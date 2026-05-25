#include "config.h"
#include "globals.h"
#include "nvs_config.h"
#include "excitation.h"
#include "adc_read.h"
#include "sync.h"
#include "tdm.h"
#include "sensing_task.h"
#include "network_task.h"

#include "nvs_flash.h"
#include "esp_log.h"
#include "freertos/FreeRTOS.h"
#include "freertos/queue.h"
#include "freertos/task.h"

static const char *TAG = "main";

/* Global result queue: scan_result_t items from sensing_task → network_task */
QueueHandle_t g_result_queue = NULL;

/* Node config is static so both tasks can hold a pointer to it safely. */
static node_config_t s_config;

void app_main(void)
{
    /* 1. NVS flash init (required before nvs_config_load) */
    esp_err_t ret = nvs_flash_init();
    if (ret == ESP_ERR_NVS_NO_FREE_PAGES ||
        ret == ESP_ERR_NVS_NEW_VERSION_FOUND) {
        ESP_ERROR_CHECK(nvs_flash_erase());
        ret = nvs_flash_init();
    }
    ESP_ERROR_CHECK(ret);

    /* 2. Load node configuration from NVS — fatal on failure */
    ret = nvs_config_load(&s_config);
    if (ret != ESP_OK) {
        ESP_LOGE(TAG, "nvs_config_load failed (%s) — restarting",
                 esp_err_to_name(ret));
        esp_restart();
    }
    ESP_LOGI(TAG, "node_id=%u, leader=%d, ssid=%s, osc=%s:%u",
             s_config.node_id, s_config.is_leader,
             s_config.wifi_ssid, s_config.osc_host, s_config.osc_port);

    /* 3. Excitation driver */
    ESP_ERROR_CHECK(excitation_init());

    /* 4. ADC / SPI driver */
    ESP_ERROR_CHECK(adc_init());

    /* 5. Sync subsystem */
    ESP_ERROR_CHECK(sync_init(s_config.is_leader));

    /* 6. Result queue */
    g_result_queue = xQueueCreate(RESULT_QUEUE_DEPTH, sizeof(scan_result_t));
    if (g_result_queue == NULL) {
        ESP_LOGE(TAG, "failed to create result queue — restarting");
        esp_restart();
    }

    /* 7. Network task (Core 0) */
    BaseType_t task_ret = xTaskCreatePinnedToCore(
        network_task,
        "network",
        NETWORK_TASK_STACK,
        &s_config,
        NETWORK_TASK_PRIO,
        NULL,
        NETWORK_TASK_CORE);
    if (task_ret != pdPASS) {
        ESP_LOGE(TAG, "failed to create network_task — restarting");
        esp_restart();
    }

    /* 8. Sensing task (Core 1) */
    task_ret = xTaskCreatePinnedToCore(
        sensing_task,
        "sensing",
        SENSING_TASK_STACK,
        &s_config,
        SENSING_TASK_PRIO,
        NULL,
        SENSING_TASK_CORE);
    if (task_ret != pdPASS) {
        ESP_LOGE(TAG, "failed to create sensing_task — restarting");
        esp_restart();
    }

    ESP_LOGI(TAG, "all tasks started");
}
