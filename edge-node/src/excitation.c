#include "excitation.h"

#include "driver/ledc.h"
#include "esp_log.h"
#include "config.h"

static const char *TAG = "excitation";

/*
 * LEDC configuration constants.
 * ESP32-WROOM-32 supports LEDC_HIGH_SPEED_MODE (not available on ESP32-S3).
 * 1-bit resolution maximises frequency divider precision for 18–24 kHz range.
 */
#define EXCITATION_SPEED_MODE   LEDC_HIGH_SPEED_MODE
#define EXCITATION_TIMER        LEDC_TIMER_0
#define EXCITATION_CHANNEL      LEDC_CHANNEL_0
#define EXCITATION_DUTY_RES     LEDC_TIMER_1_BIT
#define EXCITATION_DUTY_50PCT   1u    /* 1/2 = 50% duty cycle at 1-bit resolution */

esp_err_t excitation_init(void)
{
    ledc_timer_config_t timer = {
        .speed_mode      = EXCITATION_SPEED_MODE,
        .timer_num       = EXCITATION_TIMER,
        .duty_resolution = EXCITATION_DUTY_RES,
        .freq_hz         = 1000,        /* placeholder; overridden by excitation_start() */
        .clk_cfg         = LEDC_AUTO_CLK,
    };
    esp_err_t err = ledc_timer_config(&timer);
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "ledc_timer_config failed: %s", esp_err_to_name(err));
        return err;
    }

    ledc_channel_config_t channel = {
        .speed_mode = EXCITATION_SPEED_MODE,
        .channel    = EXCITATION_CHANNEL,
        .timer_sel  = EXCITATION_TIMER,
        .intr_type  = LEDC_INTR_DISABLE,
        .gpio_num   = PIN_EXCITATION,
        .duty       = 0,    /* start with output off */
        .hpoint     = 0,
    };
    err = ledc_channel_config(&channel);
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "ledc_channel_config failed: %s", esp_err_to_name(err));
        return err;
    }

    ESP_LOGI(TAG, "LEDC initialised: timer=%d channel=%d gpio=%d (HIGH_SPEED_MODE)",
             EXCITATION_TIMER, EXCITATION_CHANNEL, PIN_EXCITATION);
    return ESP_OK;
}

void excitation_start(uint32_t freq_hz)
{
    /* Update frequency on the running timer. */
    ESP_ERROR_CHECK(ledc_set_freq(EXCITATION_SPEED_MODE, EXCITATION_TIMER, freq_hz));

    /* Set 50% duty and apply. */
    ESP_ERROR_CHECK(ledc_set_duty(EXCITATION_SPEED_MODE, EXCITATION_CHANNEL, EXCITATION_DUTY_50PCT));
    ESP_ERROR_CHECK(ledc_update_duty(EXCITATION_SPEED_MODE, EXCITATION_CHANNEL));

    uint32_t actual_hz = ledc_get_freq(EXCITATION_SPEED_MODE, EXCITATION_TIMER);
    ESP_LOGI(TAG, "excitation started: requested=%lu Hz actual=%lu Hz, 50%% duty",
             (unsigned long)freq_hz, (unsigned long)actual_hz);
}

void excitation_stop(void)
{
    esp_err_t err = ledc_set_duty(EXCITATION_SPEED_MODE, EXCITATION_CHANNEL, 0);
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "ledc_set_duty(0) failed: %s", esp_err_to_name(err));
        return;
    }
    err = ledc_update_duty(EXCITATION_SPEED_MODE, EXCITATION_CHANNEL);
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "ledc_update_duty failed: %s", esp_err_to_name(err));
        return;
    }

    ESP_LOGD(TAG, "excitation stopped");
}
