#include "sync.h"
#include "config.h"

#include "driver/gpio.h"
#include "hal/gpio_ll.h"
#include "driver/gptimer.h"
#include "esp_log.h"
#include "esp_rom_sys.h"   /* esp_rom_delay_us */
#include "freertos/FreeRTOS.h"
#include "freertos/semphr.h"

static const char *TAG = "sync";

SemaphoreHandle_t g_sync_sem = NULL;

/* -------------------------------------------------------------------------
 * Leader path
 * -------------------------------------------------------------------------
 *
 * GPTimer fires every TDM_FRAME_MS (10 ms).  The ISR pulses PIN_SYNC HIGH
 * for ~5 µs then LOW, then gives g_sync_sem so the sensing task wakes.
 *
 * GPTimer ISRs run in IRAM (the driver guarantees this when the callback is
 * registered with ESP_INTR_FLAG_IRAM).  The callback must not call any
 * non-IRAM-safe function.
 */

static bool IRAM_ATTR timer_alarm_cb(gptimer_handle_t timer,
                                     const gptimer_alarm_event_data_t *edata,
                                     void *user_ctx)
{
    BaseType_t higher_prio_woken = pdFALSE;

    /* Pulse PIN_SYNC HIGH for ~5 µs then LOW.
     * Use gpio_ll_set_level (direct register write) instead of
     * gpio_set_level, which is not guaranteed to be in IRAM and
     * would cause a cache-miss fault from this IRAM_ATTR ISR. */
    gpio_ll_set_level(&GPIO, PIN_SYNC, 1);
    esp_rom_delay_us(5);
    gpio_ll_set_level(&GPIO, PIN_SYNC, 0);

    xSemaphoreGiveFromISR(g_sync_sem, &higher_prio_woken);
    return higher_prio_woken == pdTRUE;
}

static esp_err_t sync_init_leader(void)
{
    /* Configure PIN_SYNC as output. */
    gpio_config_t io_cfg = {
        .pin_bit_mask = (1ULL << PIN_SYNC),
        .mode         = GPIO_MODE_OUTPUT,
        .pull_up_en   = GPIO_PULLUP_DISABLE,
        .pull_down_en = GPIO_PULLDOWN_DISABLE,
        .intr_type    = GPIO_INTR_DISABLE,
    };
    ESP_RETURN_ON_ERROR(gpio_config(&io_cfg), TAG, "gpio_config leader");
    gpio_set_level(PIN_SYNC, 0);

    /* Create GPTimer: 1 µs resolution. */
    gptimer_handle_t timer = NULL;
    gptimer_config_t timer_cfg = {
        .clk_src       = GPTIMER_CLK_SRC_DEFAULT,
        .direction     = GPTIMER_COUNT_UP,
        .resolution_hz = 1000000, /* 1 MHz → 1 µs per tick */
        .intr_priority = 0,
        .flags         = { .intr_shared = 0 },
    };
    ESP_RETURN_ON_ERROR(gptimer_new_timer(&timer_cfg, &timer),
                        TAG, "gptimer_new_timer");

    /* Alarm every TDM_FRAME_MS ms, auto-reload. */
    gptimer_alarm_config_t alarm_cfg = {
        .alarm_count                = TDM_FRAME_MS * 1000ULL, /* µs */
        .reload_count               = 0,
        .flags.auto_reload_on_alarm = true,
    };
    ESP_RETURN_ON_ERROR(gptimer_set_alarm_action(timer, &alarm_cfg),
                        TAG, "gptimer_set_alarm_action");

    /* Register ISR callback with IRAM flag. */
    gptimer_event_callbacks_t cbs = {
        .on_alarm = timer_alarm_cb,
    };
    ESP_RETURN_ON_ERROR(
        gptimer_register_event_callbacks(timer, &cbs, NULL),
        TAG, "gptimer_register_event_callbacks");

    ESP_RETURN_ON_ERROR(gptimer_enable(timer), TAG, "gptimer_enable");
    ESP_RETURN_ON_ERROR(gptimer_start(timer), TAG, "gptimer_start");

    ESP_LOGI(TAG, "leader sync initialised (GPTimer, PIN_SYNC=%d)", PIN_SYNC);
    return ESP_OK;
}

/* -------------------------------------------------------------------------
 * Follower path
 * -------------------------------------------------------------------------
 *
 * PIN_SYNC input with rising-edge interrupt.  ISR gives g_sync_sem.
 */

static void IRAM_ATTR gpio_isr_handler(void *arg)
{
    BaseType_t higher_prio_woken = pdFALSE;
    xSemaphoreGiveFromISR(g_sync_sem, &higher_prio_woken);
    if (higher_prio_woken) {
        portYIELD_FROM_ISR();
    }
}

static esp_err_t sync_init_follower(void)
{
    gpio_config_t io_cfg = {
        .pin_bit_mask = (1ULL << PIN_SYNC),
        .mode         = GPIO_MODE_INPUT,
        .pull_up_en   = GPIO_PULLUP_DISABLE,
        .pull_down_en = GPIO_PULLDOWN_ENABLE,
        .intr_type    = GPIO_INTR_POSEDGE,
    };
    ESP_RETURN_ON_ERROR(gpio_config(&io_cfg), TAG, "gpio_config follower");

    /* Install global GPIO ISR service if not already installed. */
    esp_err_t ret = gpio_install_isr_service(ESP_INTR_FLAG_IRAM);
    if (ret != ESP_OK && ret != ESP_ERR_INVALID_STATE) {
        /* ESP_ERR_INVALID_STATE means it's already installed — that's fine. */
        ESP_RETURN_ON_ERROR(ret, TAG, "gpio_install_isr_service");
    }

    ESP_RETURN_ON_ERROR(
        gpio_isr_handler_add(PIN_SYNC, gpio_isr_handler, NULL),
        TAG, "gpio_isr_handler_add");

    ESP_LOGI(TAG, "follower sync initialised (GPIO rising-edge, PIN_SYNC=%d)",
             PIN_SYNC);
    return ESP_OK;
}

/* -------------------------------------------------------------------------
 * Public API
 * -------------------------------------------------------------------------*/

esp_err_t sync_init(bool is_leader)
{
    g_sync_sem = xSemaphoreCreateBinary();
    if (g_sync_sem == NULL) {
        ESP_LOGE(TAG, "failed to create g_sync_sem");
        return ESP_ERR_NO_MEM;
    }

    if (is_leader) {
        return sync_init_leader();
    } else {
        return sync_init_follower();
    }
}
