/*
 * cap-demo: Self-capacitance sensing demo using charge-amp front end.
 *
 * Circuit: TLV2372 charge amp with excitation on IN+ (pin 3) via
 * RC filter (R_exc 10k, C_exc 4.7nF), electrode on IN- (pin 2),
 * R_f 1M + C_f 10nF feedback.  Output read by ESP32 internal ADC
 * via ADC continuous mode DMA on GPIO36.
 *
 * Touch increases the electrode's parasitic capacitance, which
 * increases current through R_f and raises the output amplitude.
 * Detection is based on stdev of the sampled waveform rising above
 * an adaptive baseline.
 *
 * See Self_Cap_Concept_Node on the BSS wiki for circuit details.
 */

#include <math.h>
#include <stdbool.h>
#include <string.h>
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "esp_adc/adc_continuous.h"
#include "driver/ledc.h"
#include "driver/gpio.h"
#include "esp_log.h"
#include "esp_timer.h"

static const char *TAG = "cap-demo";

/* Excitation signal: ~30 kHz square wave on GPIO4 → R_exc → pin 3 (IN+ A) */
#define EXCITE_FREQ_HZ   30000
#define EXCITE_GPIO      4

/* ADC continuous mode DMA configuration */
#define ADC_SAMPLE_RATE  150000
#define ADC_FRAME_SIZE   2048   /* bytes; 1024 samples x 2 bytes each */
#define ADC_POOL_SIZE    8192   /* ring buffer bytes */

/* conv_frame_size must align to DMA granularity (4 bytes), not result size (2 bytes) */
_Static_assert(ADC_FRAME_SIZE % SOC_ADC_DIGI_DATA_BYTES_PER_CONV == 0,
               "ADC_FRAME_SIZE must be a multiple of SOC_ADC_DIGI_DATA_BYTES_PER_CONV");

/* Number of DMA reads per measurement window */
#ifndef GSR_RX_MODE
#define READS_PER_WINDOW  4
#endif

/*
 * Adaptive baseline tracking.
 * The baseline follows stdev with a slow EMA (ALPHA_SLOW) when no touch
 * is detected, and freezes during touch.  Touch is detected when stdev
 * rises above baseline by more than TOUCH_THRESHOLD_PCT percent.
 */
#define ALPHA_SLOW        0.1f
#define ALPHA_INIT        0.2f
#define INIT_SAMPLES      50
#define TOUCH_THRESHOLD_PCT  5.0f

#ifdef GSR_RX_MODE
/* I/Q demodulation: 5-entry reference tables for one cycle of ~30 kHz excitation.
 * At 150 ksps, one cycle = 5 samples. */
static const float COS_TABLE[5] = {1.0f, 0.3090f, -0.8090f, -0.8090f, 0.3090f};
static const float SIN_TABLE[5] = {0.0f, 0.9511f, 0.5878f, -0.5878f, -0.9511f};

#define IQ_WINDOW_SIZE   40  /* must be a multiple of 5 */
_Static_assert(IQ_WINDOW_SIZE % 5 == 0,
               "IQ_WINDOW_SIZE must be a multiple of 5 (one reference cycle = 5 samples)");
#define IQ_N_WINDOWS     4
#define IQ_TOTAL_SAMPLES (IQ_WINDOW_SIZE * IQ_N_WINDOWS)  /* 160 */
#endif

#ifndef GSR_RX_MODE
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
#endif

static adc_continuous_handle_t adc_handle = NULL;

static void init_adc_continuous(void)
{
    adc_continuous_handle_cfg_t handle_cfg = {
        .max_store_buf_size = ADC_POOL_SIZE,
        .conv_frame_size    = ADC_FRAME_SIZE,
    };
    ESP_ERROR_CHECK(adc_continuous_new_handle(&handle_cfg, &adc_handle));

    adc_digi_pattern_config_t pattern[1] = {{
        .atten     = ADC_ATTEN_DB_12,
        .channel   = ADC_CHANNEL_0,
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
     * Wait 100 ms for the ADC to settle, then discard one buffer.
     */
    vTaskDelay(pdMS_TO_TICKS(100));
    {
        static WORD_ALIGNED_ATTR uint8_t flush_buf[ADC_FRAME_SIZE];
        uint32_t br = 0;
        if (adc_continuous_read(adc_handle, flush_buf, sizeof(flush_buf), &br, 1000) != ESP_OK) {
            ESP_LOGW(TAG, "init flush read failed; first window may contain stale data");
        }
    }

    ESP_LOGI(TAG, "ADC continuous: %d sps, GPIO36 (ADC1_CH0)", ADC_SAMPLE_RATE);
}

void app_main(void)
{
#ifdef GSR_RX_MODE
    ESP_LOGI(TAG, "cap-demo starting (GSR RX mode — excitation disabled)");
    gpio_set_direction(EXCITE_GPIO, GPIO_MODE_OUTPUT);
    gpio_set_level(EXCITE_GPIO, 0);
#else
    ESP_LOGI(TAG, "cap-demo starting");
    init_ledc();
#endif
    init_adc_continuous();

    static WORD_ALIGNED_ATTR uint8_t adc_buf[ADC_FRAME_SIZE];

#ifdef GSR_RX_MODE
    ESP_LOGI(TAG, "Entering main loop (I/Q demod + stdev)");

    /* Measure true DMA sample rate: burst of reads with no processing */
    {
        int64_t t0 = esp_timer_get_time();
        long total = 0;
        int failures = 0;
        for (int r = 0; r < 100; r++) {
            uint32_t br = 0;
            esp_err_t err = adc_continuous_read(adc_handle, adc_buf,
                                                sizeof(adc_buf), &br, 1000);
            if (err == ESP_OK) {
                total += (long)(br / SOC_ADC_DIGI_RESULT_BYTES);
                failures = 0;
            } else if (++failures >= 3) {
                ESP_LOGE(TAG, "burst read failed %d times, aborting measurement", failures);
                break;
            }
        }
        int64_t elapsed = esp_timer_get_time() - t0;
        if (total > 0) {
            float fs = (float)total / ((float)elapsed / 1e6f);
            printf("measured fs=%.0f Hz (%ld samples in %.1f ms)\n",
                   fs, total, (float)elapsed / 1000.0f);
        } else {
            ESP_LOGW(TAG, "burst rate measurement aborted (no samples)");
        }
    }

    while (1) {
        uint32_t ret_num = 0;
        esp_err_t err = adc_continuous_read(adc_handle, adc_buf,
                                            sizeof(adc_buf), &ret_num, 1000);
        if (err != ESP_OK || ret_num == 0) {
            ESP_LOGE(TAG, "adc_continuous_read: err=%d ret_num=%lu",
                     err, (unsigned long)ret_num);
            continue;
        }
        int n_samples = (int)(ret_num / SOC_ADC_DIGI_RESULT_BYTES);
        if (n_samples < IQ_TOTAL_SAMPLES) {
            ESP_LOGE(TAG, "insufficient samples: %d < %d", n_samples, IQ_TOTAL_SAMPLES);
            continue;
        }

        /* Stdev over all samples in this read */
        double sum = 0.0, sum_sq = 0.0;
        for (int i = 0; i < n_samples; i++) {
            uint16_t val = ((adc_digi_output_data_t *)&adc_buf[i * SOC_ADC_DIGI_RESULT_BYTES])->type1.data;
            sum += val;
            sum_sq += (double)val * val;
        }
        double mean = sum / n_samples;
        double variance = (sum_sq / n_samples) - (mean * mean);
        float sd = (float)sqrt(variance > 0 ? variance : 0);

        /* I/Q demodulation over first IQ_TOTAL_SAMPLES samples */
        float I_avg = 0, Q_avg = 0;
        for (int w = 0; w < IQ_N_WINDOWS; w++) {
            float I_sum = 0, Q_sum = 0;
            for (int i = 0; i < IQ_WINDOW_SIZE; i++) {
                int idx = w * IQ_WINDOW_SIZE + i;
                float s = (float)(((adc_digi_output_data_t *)&adc_buf[idx * SOC_ADC_DIGI_RESULT_BYTES])->type1.data) - 2048.0f;
                I_sum += s * COS_TABLE[i % 5];
                Q_sum += s * SIN_TABLE[i % 5];
            }
            float I = I_sum / IQ_WINDOW_SIZE;
            float Q = Q_sum / IQ_WINDOW_SIZE;
            float mag = sqrtf(I * I + Q * Q);
            float phase = atan2f(Q, I) * 180.0f / (float)M_PI;
            printf("  w%d: mag=%.1f phase=%.1f\n", w, mag, phase);
            I_avg += I;
            Q_avg += Q;
        }
        I_avg /= IQ_N_WINDOWS;
        Q_avg /= IQ_N_WINDOWS;
        float mag_avg = sqrtf(I_avg * I_avg + Q_avg * Q_avg);
        float phase_avg = atan2f(Q_avg, I_avg) * 180.0f / (float)M_PI;
        printf("mag=%.1f phase=%.1f sd=%.0f mean=%.0f\n",
               mag_avg, phase_avg, sd, mean);
    }
#else
    float baseline = 0.0f;
    int sample_count = 0;
    bool touched = false;

    ESP_LOGI(TAG, "Entering main loop (adaptive baseline on stdev)");

    while (1) {
        /* Accumulate stdev over one measurement window */
        double sum = 0.0;
        double sum_sq = 0.0;
        int total_samples = 0;

        for (int r = 0; r < READS_PER_WINDOW; r++) {
            uint32_t ret_num = 0;
            esp_err_t err = adc_continuous_read(adc_handle, adc_buf,
                                                sizeof(adc_buf), &ret_num, 1000);
            if (err != ESP_OK || ret_num == 0) {
                ESP_LOGE(TAG, "adc_continuous_read: err=%d ret_num=%lu",
                         err, (unsigned long)ret_num);
                continue;
            }

            int n_samples = (int)(ret_num / SOC_ADC_DIGI_RESULT_BYTES);
            for (int i = 0; i < n_samples; i++) {
                uint16_t val = ((adc_digi_output_data_t *)&adc_buf[i * SOC_ADC_DIGI_RESULT_BYTES])->type1.data;
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
        bool now_touched = (baseline > 0) && (sd > baseline + threshold);

        /*
         * Update baseline only when not touched.  This prevents touch
         * events from dragging the baseline up, which would desensitize
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

        float pct = (baseline > 0) ? 100.0f * (sd - baseline) / baseline : 0;
        printf("sd=%.0f mean=%.0f base=%.0f delta=%.1f%% %s\n",
               sd, mean, baseline, pct, now_touched ? "TOUCH" : "");
    }
#endif
}
