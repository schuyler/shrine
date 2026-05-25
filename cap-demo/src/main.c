#include <math.h>
#include <stdbool.h>
#include <string.h>
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "driver/i2s.h"
#include "driver/ledc.h"
#include "driver/adc.h"
#include "esp_log.h"

static const char *TAG = "cap-demo";

/* Excitation signal: 30 kHz square wave on GPIO18 */
#define EXCITE_FREQ_HZ   29777
#define EXCITE_GPIO      18

/* ADC input: GPIO36 = ADC1_CHANNEL_0 */
#define ADC_CHANNEL      ADC1_CHANNEL_0

/* I2S ADC DMA sample rate */
#define SAMPLE_RATE      150000

/* DMA buffer sizing */
#define DMA_BUF_LEN      1024
#define DMA_BUF_COUNT    8

/* Number of DMA reads per measurement window */
#define READS_PER_WINDOW  4

/*
 * Adaptive baseline tracking.
 * The baseline follows stdev with a slow EMA (ALPHA_SLOW) when no touch
 * is detected, and freezes during touch.  Touch is detected when stdev
 * drops below baseline by more than TOUCH_THRESHOLD_PCT percent.
 */
#define ALPHA_SLOW        0.02f
#define ALPHA_INIT        0.2f
#define INIT_SAMPLES      50
#define TOUCH_THRESHOLD_PCT  5.0f

static void init_ledc(void)
{
    ledc_timer_config_t timer = {
        .speed_mode      = LEDC_HIGH_SPEED_MODE,
        .timer_num       = LEDC_TIMER_0,
        .duty_resolution = LEDC_TIMER_8_BIT,
        .freq_hz         = EXCITE_FREQ_HZ,
        .clk_cfg         = LEDC_AUTO_CLK,
    };
    ESP_ERROR_CHECK(ledc_timer_config(&timer));

    ledc_channel_config_t channel = {
        .speed_mode = LEDC_HIGH_SPEED_MODE,
        .channel    = LEDC_CHANNEL_0,
        .timer_sel  = LEDC_TIMER_0,
        .intr_type  = LEDC_INTR_DISABLE,
        .gpio_num   = EXCITE_GPIO,
        .duty       = 128,  /* 128/256 = 50% duty cycle */
        .hpoint     = 0,
    };
    ESP_ERROR_CHECK(ledc_channel_config(&channel));

    ESP_LOGI(TAG, "LEDC: %d Hz on GPIO%d", EXCITE_FREQ_HZ, EXCITE_GPIO);
}

static void init_i2s_adc(void)
{
    i2s_config_t i2s_cfg = {
        .mode                 = I2S_MODE_MASTER | I2S_MODE_RX | I2S_MODE_ADC_BUILT_IN,
        .sample_rate          = SAMPLE_RATE,
        .bits_per_sample      = I2S_BITS_PER_SAMPLE_16BIT,
        .channel_format       = I2S_CHANNEL_FMT_ONLY_LEFT,
        .communication_format = I2S_COMM_FORMAT_STAND_I2S,
        .intr_alloc_flags     = 0,
        .dma_buf_count        = DMA_BUF_COUNT,
        .dma_buf_len          = DMA_BUF_LEN,
        /*
         * use_apll = false: some ESP32 silicon revisions return all-zero
         * data when APLL is used in ADC-DMA mode.  The APB clock is
         * sufficient for 150 ksps and is more reliable.
         */
        .use_apll             = false,
        .tx_desc_auto_clear   = false,
        .fixed_mclk           = 0,
    };
    ESP_ERROR_CHECK(i2s_driver_install(I2S_NUM_0, &i2s_cfg, 0, NULL));

    ESP_ERROR_CHECK(adc1_config_width(ADC_WIDTH_BIT_12));
    ESP_ERROR_CHECK(adc1_config_channel_atten(ADC_CHANNEL, ADC_ATTEN_DB_12));

    ESP_ERROR_CHECK(i2s_set_adc_mode(ADC_UNIT_1, ADC1_CHANNEL_0));
    ESP_ERROR_CHECK(i2s_adc_enable(I2S_NUM_0));

    /*
     * The first buffer(s) after enable often contain stale DMA data.
     * Wait 100 ms for the ADC to settle, then discard one buffer.
     */
    vTaskDelay(pdMS_TO_TICKS(100));
    {
        static uint16_t flush_buf[DMA_BUF_LEN];
        size_t bytes_read = 0;
        i2s_read(I2S_NUM_0, flush_buf, sizeof(flush_buf), &bytes_read, portMAX_DELAY);
    }

    ESP_LOGI(TAG, "I2S ADC: %d sps, GPIO36 (ADC1_CH0)", SAMPLE_RATE);
}

void app_main(void)
{
    ESP_LOGI(TAG, "cap-demo starting");

    init_ledc();
    init_i2s_adc();

    static uint16_t dma_buf[DMA_BUF_LEN];

    float baseline = 0.0f;
    int sample_count = 0;
    bool touched = false;

    ESP_LOGI(TAG, "Entering main loop (adaptive baseline on stdev)");

    while (1) {
        /* Accumulate stdev over one measurement window */
        double sum = 0.0;
        double sum_sq = 0.0;
        int total_samples = 0;
        int chan_hist[16] = {0};

        for (int r = 0; r < READS_PER_WINDOW; r++) {
            size_t bytes_read = 0;
            esp_err_t err = i2s_read(I2S_NUM_0, dma_buf, sizeof(dma_buf),
                                     &bytes_read, portMAX_DELAY);
            if (err != ESP_OK) {
                ESP_LOGE(TAG, "i2s_read error: %d", err);
                continue;
            }

            int n_samples = (int)(bytes_read / sizeof(uint16_t));
            for (int i = 0; i < n_samples; i++) {
                chan_hist[dma_buf[i] >> 12]++;
                uint16_t val = dma_buf[i] & 0x0FFF;
                sum += val;
                sum_sq += (double)val * val;
                total_samples++;
            }
        }

        if (total_samples == 0) {
            ESP_LOGE(TAG, "no samples read, skipping window");
            continue;
        }

        double mean = sum / total_samples;
        double variance = (sum_sq / total_samples) - (mean * mean);
        float sd = (float)sqrt(variance > 0 ? variance : 0);

        /* Adaptive baseline: fast convergence during init, slow tracking after */
        float alpha = (sample_count < INIT_SAMPLES) ? ALPHA_INIT : ALPHA_SLOW;

        float threshold = baseline * (TOUCH_THRESHOLD_PCT / 100.0f);
        bool now_touched = (baseline > 0) && (sd < baseline - threshold);

        /*
         * Update baseline only when not touched.  This prevents touch
         * events from dragging the baseline down, which would desensitize
         * detection.  On release, the baseline resumes slow tracking.
         */
        if (!now_touched) {
            baseline = (baseline == 0) ? sd : baseline * (1.0f - alpha) + sd * alpha;
            sample_count++;
        }

        if (now_touched != touched) {
            touched = now_touched;
            ESP_LOGI(TAG, "touch %s", touched ? "ON" : "OFF");
        }

        float pct = (baseline > 0) ? 100.0f * (baseline - sd) / baseline : 0;
        printf("sd=%.0f mean=%.0f base=%.0f delta=%.1f%% %s\n",
               sd, mean, baseline, pct, now_touched ? "TOUCH" : "");
    }
}
