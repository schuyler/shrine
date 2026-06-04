#ifndef NETWORK_TASK_H
#define NETWORK_TASK_H

#include "esp_err.h"
#include "config.h"

/**
 * Initialize WiFi in STA mode and start connecting.
 *
 * Must be called before adc_init() — on ESP32, the ADC continuous driver's
 * I2S-DMA ISR is unconditionally registered as IRAM-safe, but calls functions
 * that live in flash.  WiFi init does flash reads (PHY cal, NVS) that disable
 * the cache, and if the ADC ISR fires during that window it panics.
 *
 * @param cfg  Node configuration with WiFi credentials.
 * @return     ESP_OK on success.
 */
esp_err_t wifi_init(const node_config_t *cfg);

/**
 * FreeRTOS task entry point for OSC output over UDP.
 *
 * Assumes WiFi is already initialized via wifi_init().
 * Runs on NETWORK_TASK_CORE (Core 0) at NETWORK_TASK_PRIO.
 *
 * @param param  Pointer to node_config_t (cast from void *).
 *               The pointer must remain valid for the lifetime of the task.
 */
void network_task(void *param);

#endif /* NETWORK_TASK_H */
