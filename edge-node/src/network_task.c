#include "network_task.h"
#include "config.h"
#include "globals.h"

#include "freertos/FreeRTOS.h"
#include "freertos/queue.h"
#include "freertos/timers.h"

#include "esp_check.h"
#include "esp_log.h"
#include "esp_event.h"
#include "esp_netif.h"
#include "esp_wifi.h"

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

    ESP_LOGI(TAG, "WiFi STA started, connecting to SSID: %s", cfg->wifi_ssid);
    ESP_RETURN_ON_ERROR(esp_wifi_connect(), TAG, "esp_wifi_connect");

    return ESP_OK;
}

/* -------------------------------------------------------------------------
 * OSC send
 * -------------------------------------------------------------------------*/

/* Generous buffer: address + type tag + 5 floats, each padded to 4 bytes. */
#define OSC_BUF_SIZE 128

static void send_osc(int sock, const struct sockaddr_in *dest,
                     const node_config_t *cfg, const scan_result_t *result)
{
    char addr[32];
    snprintf(addr, sizeof(addr), "/shrine/node/%u", cfg->node_id);

    char buf[OSC_BUF_SIZE];
    int  len = tosc_writeMessage(buf, sizeof(buf), addr, "fffff",
                                 result->self_stdev,
                                 result->self_carrier_mag,
                                 result->gsr_mag[0],
                                 result->gsr_mag[1],
                                 result->gsr_mag[2]);
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

    /* --- Main loop ----------------------------------------------------- */
    scan_result_t result;
    while (1) {
        if (xQueueReceive(g_result_queue, &result, portMAX_DELAY) == pdTRUE) {
            send_osc(sock, &dest, cfg, &result);
        }
    }
}
