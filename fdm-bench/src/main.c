/*
 * fdm-bench: Frequency-division multiplexing capacitive sensing bench test.
 *
 * Each node occupies a distinct spectral bin derived from measured fs:
 *   k = 180 + node_id * 20
 *   f_exc = k * fs / WINDOW_SIZE
 *
 * With ADC_SAMPLE_RATE=220000 and the I2S 9/11 ratio:
 *   actual fs ~ 180000 Hz
 *   WINDOW_SIZE = 1800  => bin spacing = 100 Hz
 *   node 0: k=180, f~18000 Hz
 *   node 1: k=200, f~20000 Hz
 *   node 2: k=220, f~22000 Hz
 *   node 3: k=240, f~24000 Hz
 *
 * The bench test measures:
 *   Q1: ADC noise floor vs. signal level at each FDM bin
 *   Q2: Cross-talk between adjacent FDM channels
 *   Q3: Temporal stability of magnitude over a 60-second window
 *   Q4: LEDC frequency quantization error (actual vs. requested bin)
 *
 * Serial commands (non-blocking, polled once per DMA read):
 *   'd' — dump last complete 1800-sample window as decimal ints, one per line, then "END"
 *   'r' — resume continuous mag/sd output
 *
 * NVS key 'node_id' in namespace 'shrine' selects the node (0..3).
 * Flash with: idf.py -p PORT nvs-flash --nvs-partition-table-csv nvs/nodeN.csv
 */

#include <math.h>
#include <stdbool.h>
#include <string.h>
#include <fcntl.h>
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "esp_adc/adc_continuous.h"
#include "driver/ledc.h"
#include "driver/gpio.h"
#include "esp_log.h"
#include "esp_timer.h"
#include "nvs_flash.h"
#include "nvs.h"

static const char *TAG = "fdm-bench";

/* ADC continuous mode DMA configuration */
#define ADC_SAMPLE_RATE     220000  /* requested; actual ~180 ksps (9/11 ratio) */
#define ADC_FRAME_SIZE      2048    /* bytes; 1024 samples x 2 bytes each */
#define ADC_POOL_SIZE       8192    /* ring buffer bytes */

/* conv_frame_size must align to DMA granularity (4 bytes) */
_Static_assert(ADC_FRAME_SIZE % SOC_ADC_DIGI_DATA_BYTES_PER_CONV == 0,
               "ADC_FRAME_SIZE must be a multiple of SOC_ADC_DIGI_DATA_BYTES_PER_CONV");

/* Excitation output GPIO */
#define EXCITE_GPIO         4

/* I/Q demodulation window: must equal LEDC period in samples at actual fs */
#define WINDOW_SIZE         1800

/* fs calibration: number of DMA burst reads (200 reads x ~1024 samples ~ 200k samples) */
#define CAL_BURST_READS     200

/* NCO renormalization interval — matches cap-demo's MCP3201 PLL path */
#define NCO_RENORM_INTERVAL 64

static adc_continuous_handle_t adc_handle = NULL;

/* DMA receive buffer — must be word-aligned for DMA */
static WORD_ALIGNED_ATTR uint8_t adc_buf[ADC_FRAME_SIZE];

/* Rolling accumulation buffer: collects samples across DMA reads */
static uint16_t sample_buf[WINDOW_SIZE];

/* Snapshot of last complete window — safe to dump while next window accumulates */
static uint16_t window_buf[WINDOW_SIZE];

static int  buf_pos = 0;
static bool paused  = false;

/* -------------------------------------------------------------------------
 * ADC init
 * ------------------------------------------------------------------------- */
static void init_adc_continuous(void)
{
    adc_continuous_handle_cfg_t handle_cfg = {
        .max_store_buf_size = ADC_POOL_SIZE,
        .conv_frame_size    = ADC_FRAME_SIZE,
    };
    ESP_ERROR_CHECK(adc_continuous_new_handle(&handle_cfg, &adc_handle));

    adc_digi_pattern_config_t pattern[1] = {{
        .atten     = ADC_ATTEN_DB_12,
        .channel   = ADC_CHANNEL_0,   /* GPIO36 = ADC1_CH0 */
        .unit      = ADC_UNIT_1,
        .bit_width = ADC_BITWIDTH_12,
    }};
    adc_continuous_config_t dig_cfg = {
        .pattern_num    = 1,
        .adc_pattern    = pattern,
        .sample_freq_hz = ADC_SAMPLE_RATE,
        .conv_mode      = ADC_CONV_SINGLE_UNIT_1,
        .format         = ADC_DIGI_OUTPUT_FORMAT_TYPE1,
    };
    ESP_ERROR_CHECK(adc_continuous_config(adc_handle, &dig_cfg));
    ESP_ERROR_CHECK(adc_continuous_start(adc_handle));

    /*
     * The first buffer(s) after enable often contain stale DMA data.
     * Wait 100 ms for the ADC to settle, then discard one frame.
     */
    vTaskDelay(pdMS_TO_TICKS(100));
    {
        static WORD_ALIGNED_ATTR uint8_t flush_buf[ADC_FRAME_SIZE];
        uint32_t br = 0;
        if (adc_continuous_read(adc_handle, flush_buf, sizeof(flush_buf), &br, 1000) != ESP_OK) {
            ESP_LOGW(TAG, "init flush read failed; first window may contain stale data");
        }
    }

    ESP_LOGI(TAG, "ADC continuous: %d sps requested, GPIO36 (ADC1_CH0)", ADC_SAMPLE_RATE);
}

/* -------------------------------------------------------------------------
 * fs calibration
 *
 * Burst-reads CAL_BURST_READS DMA frames and times them to measure the
 * actual sample rate delivered by the I2S DMA engine (9/11 of requested).
 * Returns 0.0f on failure; caller must abort.
 * ------------------------------------------------------------------------- */
static float calibrate_fs(adc_continuous_handle_t handle,
                           uint8_t *buf, int frame_size)
{
    /* Flush stale DMA data before timing */
    for (int i = 0; i < 5; i++) {
        uint32_t br = 0;
        adc_continuous_read(handle, buf, frame_size, &br, 1000);
    }

    int64_t t0 = esp_timer_get_time();
    long total_samples = 0;
    for (int r = 0; r < CAL_BURST_READS; r++) {
        uint32_t br = 0;
        esp_err_t err = adc_continuous_read(handle, buf, frame_size, &br, 1000);
        if (err == ESP_OK)
            total_samples += (long)(br / SOC_ADC_DIGI_RESULT_BYTES);
    }
    int64_t elapsed_us = esp_timer_get_time() - t0;

    if (total_samples == 0 || elapsed_us == 0) return 0.0f;
    return (float)total_samples / ((float)elapsed_us / 1e6f);
}

/* -------------------------------------------------------------------------
 * process_window: I/Q demodulation at bin k
 *
 * Uses incremental NCO rotation (no trig table) with periodic renorm to
 * prevent magnitude drift from floating-point accumulation error.
 * DC is removed per-sample by subtracting the window mean.
 * ------------------------------------------------------------------------- */
static void process_window(const uint16_t *buf, int n, int k)
{
    /* Mean and stdev */
    double sum = 0.0, sum_sq = 0.0;
    for (int i = 0; i < n; i++) {
        double v = buf[i];
        sum    += v;
        sum_sq += v * v;
    }
    double mean     = sum / n;
    double variance = (sum_sq / n) - (mean * mean);
    float  sd       = sqrtf(variance > 0.0 ? (float)variance : 0.0f);

    /* I/Q demodulation via incremental NCO rotation.
     * Standard DFT: X[k] = sum(x[n] * e^{-j*2*pi*k*n/N})
     * Negative rotation: negate sin_step so the phasor advances as e^{-j*theta}. */
    float cos_step =  cosf(2.0f * (float)M_PI * (float)k / (float)n);
    float sin_step = -sinf(2.0f * (float)M_PI * (float)k / (float)n);

    float rc = 1.0f, rs = 0.0f;  /* NCO phasor: cos and sin components */
    float I = 0.0f, Q = 0.0f;
    int renorm_counter = 0;

    for (int i = 0; i < n; i++) {
        float s = (float)buf[i] - (float)mean;  /* DC removal */
        I += s * rc;
        Q += s * rs;

        /* Rotate NCO phasor by one step */
        float new_rc = rc * cos_step - rs * sin_step;
        float new_rs = rs * cos_step + rc * sin_step;
        rc = new_rc;
        rs = new_rs;

        /* Renormalize every NCO_RENORM_INTERVAL samples to prevent drift */
        if (++renorm_counter >= NCO_RENORM_INTERVAL) {
            float mag = sqrtf(rc * rc + rs * rs);
            rc /= mag;
            rs /= mag;
            renorm_counter = 0;
        }
    }

    float mag = sqrtf(I * I + Q * Q) / (float)n;
    printf("mag=%.1f sd=%.0f mean=%.0f n=%d\n", mag, sd, mean, n);
}

/* -------------------------------------------------------------------------
 * dump_window: print last complete window as decimal ints, one per line
 * ------------------------------------------------------------------------- */
static void dump_window(const uint16_t *buf)
{
    for (int i = 0; i < WINDOW_SIZE; i++) {
        printf("%u\n", (unsigned)buf[i]);
    }
    printf("END\n");
}

/* -------------------------------------------------------------------------
 * app_main
 * ------------------------------------------------------------------------- */
void app_main(void)
{
    /* --- NVS: read node_id --- */
    esp_err_t nvs_err = nvs_flash_init();
    ESP_LOGI(TAG, "nvs_flash_init: %s (0x%x)", esp_err_to_name(nvs_err), nvs_err);
    if (nvs_err == ESP_ERR_NVS_NO_FREE_PAGES ||
        nvs_err == ESP_ERR_NVS_NEW_VERSION_FOUND) {
        ESP_LOGW(TAG, "NVS erase triggered by init error — provisioned data lost");
        ESP_ERROR_CHECK(nvs_flash_erase());
        nvs_err = nvs_flash_init();
    }
    ESP_ERROR_CHECK(nvs_err);

    uint8_t node_id = 0;
    nvs_handle_t nvs;
    esp_err_t err = nvs_open("shrine", NVS_READONLY, &nvs);
    ESP_LOGI(TAG, "nvs_open('shrine'): %s (0x%x)", esp_err_to_name(err), err);
    if (err == ESP_OK) {
        err = nvs_get_u8(nvs, "node_id", &node_id);
        if (err != ESP_OK) {
            ESP_LOGW(TAG, "node_id not found in NVS: %s, defaulting to 0",
                     esp_err_to_name(err));
            node_id = 0;
        }
        nvs_close(nvs);
    } else {
        ESP_LOGW(TAG, "NVS namespace 'shrine' not found, defaulting node_id=0");
        node_id = 0;
    }

    /* --- ADC init --- */
    init_adc_continuous();

    /* --- Calibrate actual sample rate --- */
    float fs = calibrate_fs(adc_handle, adc_buf, ADC_FRAME_SIZE);
    if (fs < 1.0f) {
        ESP_LOGE(TAG, "fs calibration failed");
        return;
    }
    ESP_LOGI(TAG, "fs_measured=%.1f", fs);

    /* --- Derive carrier bin and excitation frequency --- */
    int k = 180 + (int)node_id * 20;
    float f_exc_req = (float)k * fs / (float)WINDOW_SIZE;

    /* --- LEDC excitation ---
     *
     * Use LEDC_HIGH_SPEED_MODE: correct for ESP32-WROOM-32 (this target).
     * LEDC_LOW_SPEED_MODE is required only on ESP32-S3 (edge-node target).
     */
    ledc_timer_config_t timer = {
        .speed_mode      = LEDC_HIGH_SPEED_MODE,
        .timer_num       = LEDC_TIMER_0,
        .duty_resolution = LEDC_TIMER_1_BIT,
        .freq_hz         = (uint32_t)f_exc_req,
        .clk_cfg         = LEDC_AUTO_CLK,
    };
    ESP_ERROR_CHECK(ledc_timer_config(&timer));

    ledc_channel_config_t channel = {
        .speed_mode = LEDC_HIGH_SPEED_MODE,
        .channel    = LEDC_CHANNEL_0,
        .timer_sel  = LEDC_TIMER_0,
        .intr_type  = LEDC_INTR_DISABLE,
        .gpio_num   = EXCITE_GPIO,
        .duty       = 1,    /* 1/2 = 50% duty cycle at 1-bit resolution */
        .hpoint     = 0,
    };
    ESP_ERROR_CHECK(ledc_channel_config(&channel));

    /* Read back actual frequency — central to Q4 (LEDC quantization) bench test */
    uint32_t f_exc_actual = ledc_get_freq(LEDC_HIGH_SPEED_MODE, LEDC_TIMER_0);

    printf("node=%u k=%d f_exc_req=%.1f f_exc_actual=%lu fs=%.1f\n",
           (unsigned)node_id, k, f_exc_req, (unsigned long)f_exc_actual, fs);

    /* --- Set stdin non-blocking for serial command polling ---
     *
     * Uses VFS layer directly; avoids uart_driver_install() which would
     * conflict with ESP-IDF's default console driver on UART0.
     */
    fcntl(fileno(stdin), F_SETFL, O_NONBLOCK);

    ESP_LOGI(TAG, "Entering main loop (FDM I/Q demod, bin k=%d)", k);

    /* --- Main loop --- */
    while (1) {
        uint32_t ret_num = 0;
        esp_err_t read_err = adc_continuous_read(adc_handle, adc_buf,
                                                 sizeof(adc_buf), &ret_num, 1000);
        if (read_err != ESP_OK || ret_num == 0) {
            ESP_LOGE(TAG, "adc_continuous_read: err=%d ret_num=%lu",
                     read_err, (unsigned long)ret_num);
            continue;
        }

        /* Poll for serial command (non-blocking) */
        int ch = fgetc(stdin);
        if (ch == 'd') {
            paused = true;
            dump_window(window_buf);
        } else if (ch == 'r') {
            paused = false;
        }

        /*
         * Parse DMA result into sample_buf with carry-over.
         *
         * Each DMA read yields up to 1024 samples; WINDOW_SIZE=1800 spans
         * ~1.75 reads.  When buf_pos reaches WINDOW_SIZE mid-loop, the
         * window is snapshotted and buf_pos resets to 0.  The remaining
         * samples in the same DMA read naturally carry over into the next
         * window — no samples are dropped between windows.
         */
        int n_samples = (int)(ret_num / SOC_ADC_DIGI_RESULT_BYTES);
        for (int i = 0; i < n_samples; i++) {
            uint16_t val = ((adc_digi_output_data_t *)
                &adc_buf[i * SOC_ADC_DIGI_RESULT_BYTES])->type1.data;
            sample_buf[buf_pos++] = val;

            if (buf_pos >= WINDOW_SIZE) {
                /* Snapshot completed window before resetting */
                memcpy(window_buf, sample_buf, WINDOW_SIZE * sizeof(uint16_t));
                if (!paused) {
                    process_window(window_buf, WINDOW_SIZE, k);
                }
                buf_pos = 0;
            }
        }
    }
}
