#ifndef SYNC_H
#define SYNC_H

#include <stdbool.h>
#include "esp_err.h"
#include "freertos/FreeRTOS.h"
#include "freertos/semphr.h"

/**
 * Binary semaphore given every TDM_FRAME_MS (10 ms) by the sync ISR.
 *
 * Leader path: GPTimer alarm ISR pulses PIN_SYNC then gives the semaphore.
 * Follower path: GPIO rising-edge ISR on PIN_SYNC gives the semaphore.
 *
 * Declared extern here; defined in sync.c.
 */
extern SemaphoreHandle_t g_sync_sem;

/**
 * Initialise the sync subsystem.
 *
 * @param is_leader  true  → configure GPTimer + PIN_SYNC output
 *                   false → configure PIN_SYNC input with rising-edge ISR
 *
 * @return ESP_OK on success, error code otherwise.
 */
esp_err_t sync_init(bool is_leader);

#endif /* SYNC_H */
