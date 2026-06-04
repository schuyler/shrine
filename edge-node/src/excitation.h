#ifndef EXCITATION_H
#define EXCITATION_H

#include <stdint.h>
#include "esp_err.h"

/**
 * Configure LEDC timer and channel for excitation output.
 * Does not start the signal; call excitation_start() when ready.
 *
 * Uses LEDC_HIGH_SPEED_MODE (required on ESP32, not available on ESP32-S3).
 * Timer 0, Channel 0, GPIO PIN_EXCITATION (GPIO 4).
 */
esp_err_t excitation_init(void);

/**
 * Set the excitation frequency and start the output at 50% duty cycle.
 *
 * @param freq_hz  Desired frequency in Hz.
 */
void excitation_start(uint32_t freq_hz);

/**
 * Stop the excitation output by setting duty to 0 (pin held LOW).
 */
void excitation_stop(void);

#endif /* EXCITATION_H */
