#include "adc_read.h"
#include "config.h"

#include "esp_adc/adc_continuous.h"
#include "esp_log.h"
#include "esp_timer.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"

static const char *TAG = "adc_read";

#define CAL_BURST_READS  200

/* conv_frame_size must align to DMA granularity */
_Static_assert(ADC_FRAME_SIZE % SOC_ADC_DIGI_DATA_BYTES_PER_CONV == 0,
               "ADC_FRAME_SIZE must be a multiple of SOC_ADC_DIGI_DATA_BYTES_PER_CONV");

static adc_continuous_handle_t s_adc = NULL;

esp_err_t adc_init(void)
{
    adc_continuous_handle_cfg_t handle_cfg = {
        .max_store_buf_size = ADC_POOL_SIZE,
        .conv_frame_size    = ADC_FRAME_SIZE,
    };
    esp_err_t err = adc_continuous_new_handle(&handle_cfg, &s_adc);
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "adc_continuous_new_handle failed: %s", esp_err_to_name(err));
        return err;
    }

    adc_digi_pattern_config_t pattern[1] = {{
        .atten     = ADC_ATTEN_DB_12,
        .channel   = ADC_CHANNEL_0,    /* GPIO36 = ADC1_CH0 on WROOM-32 */
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
    err = adc_continuous_config(s_adc, &dig_cfg);
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "adc_continuous_config failed: %s", esp_err_to_name(err));
        adc_continuous_deinit(s_adc);
        s_adc = NULL;
        return err;
    }

    err = adc_continuous_start(s_adc);
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "adc_continuous_start failed: %s", esp_err_to_name(err));
        adc_continuous_deinit(s_adc);
        s_adc = NULL;
        return err;
    }

    /* Wait 100 ms and discard one frame to flush stale DMA data. */
    vTaskDelay(pdMS_TO_TICKS(100));
    {
        static WORD_ALIGNED_ATTR uint8_t flush_buf[ADC_FRAME_SIZE];
        uint32_t br = 0;
        if (adc_continuous_read(s_adc, flush_buf, sizeof(flush_buf), &br, 1000) != ESP_OK) {
            ESP_LOGW(TAG, "init flush read failed; first window may contain stale data");
        }
    }

    ESP_LOGI(TAG, "ADC continuous: %d sps requested, GPIO36 (ADC1_CH0), TYPE1 format",
             ADC_SAMPLE_RATE);
    return ESP_OK;
}

esp_err_t adc_calibrate_fs(float *fs_out)
{
    /* Flush stale data before timing */
    static WORD_ALIGNED_ATTR uint8_t buf[ADC_FRAME_SIZE];
    for (int i = 0; i < 5; i++) {
        uint32_t br = 0;
        adc_continuous_read(s_adc, buf, ADC_FRAME_SIZE, &br, 1000);
    }

    int64_t t0 = esp_timer_get_time();
    long total_samples = 0;
    for (int r = 0; r < CAL_BURST_READS; r++) {
        uint32_t br = 0;
        esp_err_t err = adc_continuous_read(s_adc, buf, ADC_FRAME_SIZE, &br, 1000);
        if (err == ESP_OK) {
            total_samples += (long)(br / SOC_ADC_DIGI_RESULT_BYTES);
        }
    }
    int64_t elapsed_us = esp_timer_get_time() - t0;

    if (total_samples == 0 || elapsed_us == 0) {
        ESP_LOGE(TAG, "fs calibration failed: total_samples=%ld elapsed_us=%lld",
                 total_samples, elapsed_us);
        return ESP_FAIL;
    }

    *fs_out = (float)total_samples / ((float)elapsed_us / 1e6f);
    ESP_LOGI(TAG, "fs_measured=%.1f Hz", *fs_out);
    return ESP_OK;
}

esp_err_t adc_read_frame(uint8_t *buf, uint32_t *bytes_read, uint32_t timeout_ms)
{
    return adc_continuous_read(s_adc, buf, ADC_FRAME_SIZE, bytes_read, timeout_ms);
}

void adc_stop(void)
{
    if (s_adc != NULL) {
        adc_continuous_stop(s_adc);
        adc_continuous_deinit(s_adc);
        s_adc = NULL;
    }
}
