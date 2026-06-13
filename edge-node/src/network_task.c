#include "network_task.h"
#include "config.h"
#include "calibration.h"
#include "globals.h"

#include "freertos/FreeRTOS.h"
#include "freertos/queue.h"
#include "freertos/timers.h"

#include "esp_check.h"
#include "esp_log.h"
#include "esp_event.h"
#include "esp_netif.h"
#include "esp_wifi.h"
#include "mdns.h"

#include "lwip/sockets.h"
#include "lwip/netdb.h"

#include "tinyosc.h"

#include <string.h>
#include <stdio.h>

static const char *TAG = "network";

/* -------------------------------------------------------------------------
 * Reconnect backoff state
 * -------------------------------------------------------------------------*/

#define BACKOFF_INIT_MS    1000
#define BACKOFF_MAX_MS    30000

static TimerHandle_t  s_reconnect_timer = NULL;
static uint32_t       s_backoff_ms      = BACKOFF_INIT_MS;
static wifi_config_t  s_wifi_cfg;       /* stored at init for reconnect */
static char      s_mdns_hostname[16];   /* "node-255\0" max 9 chars */
static uint16_t  s_mdns_osc_port;

static void reconnect_timer_cb(TimerHandle_t timer)
{
    ESP_LOGI(TAG, "attempting WiFi reconnect (backoff=%lu ms)", s_backoff_ms);
    esp_wifi_connect();

    /* Double backoff, cap at maximum. */
    s_backoff_ms = (s_backoff_ms * 2 > BACKOFF_MAX_MS)
                   ? BACKOFF_MAX_MS : s_backoff_ms * 2;
}

static void schedule_reconnect(void)
{
    if (s_reconnect_timer == NULL) {
        s_reconnect_timer = xTimerCreate("wifi_reconnect",
                                         pdMS_TO_TICKS(s_backoff_ms),
                                         pdFALSE,        /* one-shot */
                                         NULL,
                                         reconnect_timer_cb);
    } else {
        xTimerChangePeriod(s_reconnect_timer,
                           pdMS_TO_TICKS(s_backoff_ms),
                           pdMS_TO_TICKS(100));
    }
    xTimerStart(s_reconnect_timer, pdMS_TO_TICKS(100));
}

/* -------------------------------------------------------------------------
 * WiFi event handler
 * -------------------------------------------------------------------------*/

static void wifi_event_handler(void *arg, esp_event_base_t event_base,
                                int32_t event_id, void *event_data)
{
    if (event_base == WIFI_EVENT && event_id == WIFI_EVENT_STA_DISCONNECTED) {
        ESP_LOGW(TAG, "WiFi disconnected — scheduling reconnect in %lu ms",
                 s_backoff_ms);
        schedule_reconnect();
    } else if (event_base == IP_EVENT && event_id == IP_EVENT_STA_GOT_IP) {
        ip_event_got_ip_t *ev = (ip_event_got_ip_t *)event_data;
        ESP_LOGI(TAG, "got IP: " IPSTR, IP2STR(&ev->ip_info.ip));
        /* Reset backoff on successful connection. */
        s_backoff_ms = BACKOFF_INIT_MS;
        /* Cancel any pending reconnect timer now that we have an IP. */
        if (s_reconnect_timer != NULL) {
            xTimerStop(s_reconnect_timer, 0);
        }

        /* Register mDNS hostname and OSC service.
         * mdns_service_remove handles the reconnect case (returns
         * ESP_ERR_NOT_FOUND harmlessly on first connect). */
        esp_err_t rm_ret = mdns_service_remove("_osc", "_udp");
        if (rm_ret != ESP_OK && rm_ret != ESP_ERR_NOT_FOUND) {
            ESP_LOGW(TAG, "mdns_service_remove unexpected: %s",
                     esp_err_to_name(rm_ret));
        }

        esp_err_t h_ret = mdns_hostname_set(s_mdns_hostname);
        if (h_ret != ESP_OK) {
            ESP_LOGW(TAG, "mdns_hostname_set failed: %s",
                     esp_err_to_name(h_ret));
        }

        esp_err_t s_ret = mdns_service_add(NULL, "_osc", "_udp",
                                           s_mdns_osc_port, NULL, 0);
        if (s_ret != ESP_OK) {
            ESP_LOGW(TAG, "mdns_service_add failed: %s",
                     esp_err_to_name(s_ret));
        }

        ESP_LOGI(TAG, "mDNS: %s.local _osc._udp port %u",
                 s_mdns_hostname, s_mdns_osc_port);
    }
}

/* -------------------------------------------------------------------------
 * WiFi init
 * -------------------------------------------------------------------------*/

esp_err_t wifi_init(const node_config_t *cfg)
{
    ESP_RETURN_ON_ERROR(esp_netif_init(), TAG, "esp_netif_init");
    ESP_RETURN_ON_ERROR(esp_event_loop_create_default(), TAG,
                        "esp_event_loop_create_default");

    esp_netif_create_default_wifi_sta();

    /* mDNS — store config for event handler, init the stack. */
    snprintf(s_mdns_hostname, sizeof(s_mdns_hostname),
             "node-%u", cfg->node_id);
    s_mdns_osc_port = cfg->osc_port;

    ESP_RETURN_ON_ERROR(mdns_init(), TAG, "mdns_init");

    wifi_init_config_t wifi_init_cfg = WIFI_INIT_CONFIG_DEFAULT();
    ESP_RETURN_ON_ERROR(esp_wifi_init(&wifi_init_cfg), TAG, "esp_wifi_init");

    ESP_RETURN_ON_ERROR(
        esp_event_handler_register(WIFI_EVENT, ESP_EVENT_ANY_ID,
                                   wifi_event_handler, NULL),
        TAG, "register WIFI_EVENT handler");
    ESP_RETURN_ON_ERROR(
        esp_event_handler_register(IP_EVENT, IP_EVENT_STA_GOT_IP,
                                   wifi_event_handler, NULL),
        TAG, "register IP_EVENT handler");

    memset(&s_wifi_cfg, 0, sizeof(s_wifi_cfg));
    strncpy((char *)s_wifi_cfg.sta.ssid,     cfg->wifi_ssid,
            sizeof(s_wifi_cfg.sta.ssid) - 1);
    strncpy((char *)s_wifi_cfg.sta.password, cfg->wifi_pass,
            sizeof(s_wifi_cfg.sta.password) - 1);
    s_wifi_cfg.sta.threshold.authmode = WIFI_AUTH_WPA2_PSK;

    ESP_RETURN_ON_ERROR(esp_wifi_set_mode(WIFI_MODE_STA), TAG,
                        "esp_wifi_set_mode");
    ESP_RETURN_ON_ERROR(esp_wifi_set_config(WIFI_IF_STA, &s_wifi_cfg), TAG,
                        "esp_wifi_set_config");
    ESP_RETURN_ON_ERROR(esp_wifi_start(), TAG, "esp_wifi_start");
    ESP_RETURN_ON_ERROR(esp_wifi_set_ps(WIFI_PS_NONE), TAG,
                        "esp_wifi_set_ps");

    ESP_LOGI(TAG, "WiFi STA started (power save off), connecting to SSID: %s",
             cfg->wifi_ssid);
    ESP_RETURN_ON_ERROR(esp_wifi_connect(), TAG, "esp_wifi_connect");

    return ESP_OK;
}

/* -------------------------------------------------------------------------
 * OSC send
 * -------------------------------------------------------------------------*/

/* Generous buffer: address + type tag + 5 floats, each padded to 4 bytes. */
#define OSC_BUF_SIZE 128

static void send_osc(int sock, const struct sockaddr_in *dest,
                     const node_config_t *cfg,
                     const float cal_values[CAL_NUM_CHANNELS],
                     float carrier_mag)
{
    char addr[32];
    snprintf(addr, sizeof(addr), "/shrine/node/%u", cfg->node_id);

    char buf[OSC_BUF_SIZE];
    int  len = tosc_writeMessage(buf, sizeof(buf), addr, "fffff",
                                 cal_values[0],     /* calibrated self_stdev */
                                 carrier_mag,        /* passthrough */
                                 cal_values[1],      /* calibrated gsr_mag[0] */
                                 cal_values[2],      /* calibrated gsr_mag[1] */
                                 cal_values[3]);     /* calibrated gsr_mag[2] */
    if (len < 0) {
        ESP_LOGD(TAG, "tosc_writeMessage: buffer too small");
        return;
    }

    int sent = sendto(sock, buf, len, 0,
                      (const struct sockaddr *)dest, sizeof(*dest));
    if (sent < 0) {
        ESP_LOGD(TAG, "sendto failed: errno=%d", errno);
    }
}

/* -------------------------------------------------------------------------
 * FFT spectrum OSC send
 * -------------------------------------------------------------------------*/

/* Separate buffer for FFT messages — the 1024-byte blob doesn't fit in
 * OSC_BUF_SIZE (128 bytes) and we don't want to enlarge the hot-path buffer. */
#define FFT_OSC_BUF_SIZE 1200

static void send_fft_osc(int sock, const struct sockaddr_in *dest,
                          const node_config_t *cfg)
{
    char addr[40];
    snprintf(addr, sizeof(addr), "/shrine/node/%u/fft", cfg->node_id);

    char buf[FFT_OSC_BUF_SIZE];
    int len = tosc_writeMessage(buf, sizeof(buf), addr, "b",
                                (void *)g_fft_spectrum, (int)FFT_BINS);
    if (len < 0) {
        ESP_LOGD(TAG, "tosc_writeMessage (FFT): buffer too small");
        return;
    }

    int sent = sendto(sock, buf, len, 0,
                      (const struct sockaddr *)dest, sizeof(*dest));
    if (sent < 0) {
        ESP_LOGD(TAG, "sendto (FFT) failed: errno=%d", errno);
    }
}

/* -------------------------------------------------------------------------
 * network_task
 * -------------------------------------------------------------------------*/

void network_task(void *param)
{
    node_config_t *cfg = (node_config_t *)param;

    ESP_LOGI(TAG, "starting on node %u", cfg->node_id);

    /* WiFi was already initialized in app_main() before the ADC continuous
     * driver started — see wifi_init() comment in network_task.h. */

    /* --- Create UDP socket --------------------------------------------- */
    int sock = socket(AF_INET, SOCK_DGRAM, IPPROTO_UDP);
    if (sock < 0) {
        ESP_LOGE(TAG, "socket() failed: errno=%d", errno);
        vTaskDelete(NULL);
        return;
    }

    int broadcast = 1;
    setsockopt(sock, SOL_SOCKET, SO_BROADCAST, &broadcast, sizeof(broadcast));

    struct sockaddr_in dest;
    memset(&dest, 0, sizeof(dest));
    dest.sin_family      = AF_INET;
    dest.sin_port        = htons(cfg->osc_port);
    dest.sin_addr.s_addr = inet_addr(cfg->osc_host);

    ESP_LOGI(TAG, "UDP socket ready, sending OSC to %s:%u",
             cfg->osc_host, cfg->osc_port);

    /* --- Calibration state ---------------------------------------------- */
    cal_state_t cal;
    calibration_init(&cal, cfg);

    /* --- Main loop: time-gated accumulation ----------------------------- */
    scan_result_t result;
    float cal_values[CAL_NUM_CHANNELS];
    float carrier_mag;

    /* Accumulation state for report-rate decimation. */
    TickType_t last_send = xTaskGetTickCount();
    TickType_t interval  = pdMS_TO_TICKS(cfg->osc_report_ms);
    float peak_stdev     = 0.0f;
    float latest_cal[CAL_NUM_CHANNELS];
    float latest_carrier = 0.0f;
    bool  have_data      = false;

    memset(latest_cal, 0, sizeof(latest_cal));

    while (1) {
        /* Drain the queue at full speed — no backpressure. Use a short
         * timeout so we can check the report timer even when the queue
         * is temporarily empty. */
        TickType_t wait = have_data
            ? 0
            : pdMS_TO_TICKS(cfg->osc_report_ms);

        if (xQueueReceive(g_result_queue, &result, wait) == pdTRUE) {
            calibration_apply(&cal, &result, cal_values, &carrier_mag);

            /* Peak-hold on stdev (don't miss touch onsets). */
            if (cal_values[0] > peak_stdev) {
                peak_stdev = cal_values[0];
            }

            /* Latest-value on carrier_mag and GSR magnitudes (slow-changing). */
            for (int i = 0; i < CAL_NUM_CHANNELS; i++) {
                latest_cal[i] = cal_values[i];
            }
            latest_carrier = carrier_mag;
            have_data = true;
        }

        /* Time to send? */
        TickType_t now = xTaskGetTickCount();
        if (have_data && (now - last_send) >= interval) {
            /* Overwrite stdev channel with peak-held value. */
            latest_cal[0] = peak_stdev;

            send_osc(sock, &dest, cfg, latest_cal, latest_carrier);

            /* Send FFT spectrum if ready (every ~5s from sensing task). */
            if (g_fft_ready) {
                send_fft_osc(sock, &dest, cfg);
                g_fft_ready = false;
            }

            /* Reset accumulation state. */
            peak_stdev = 0.0f;
            have_data  = false;
            last_send  = now;
        }
    }
}
