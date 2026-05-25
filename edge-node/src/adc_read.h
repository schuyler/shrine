#ifndef ADC_READ_H
#define ADC_READ_H

#include <stdint.h>
#include <stdbool.h>
#include "esp_err.h"

/**
 * Initialise the ADC subsystem.
 *
 * When USE_INTERNAL_ADC is defined, configures ESP32-S3 oneshot ADC on
 * ADC1_CH0 (GPIO 1).  Otherwise, configures SPI2_HOST for the MCP3201
 * external ADC using pins from config.h.
 */
esp_err_t adc_init(void);

/**
 * Acquire exclusive access to the ADC for tight-loop polling.
 * Must be called before adc_read_sample() / adc_read_into_buffer().
 */
void adc_acquire(void);

/**
 * Read a single 12-bit ADC sample.
 *
 * Must be called between adc_acquire() and adc_release().
 *
 * @return 12-bit sample value (0-4095), or 0 on failure.
 */
uint16_t adc_read_sample(void);

/**
 * Fill buf with count 12-bit samples via a tight polling loop.
 *
 * Must be called between adc_acquire() and adc_release().
 *
 * @param buf    Destination array (must hold at least count elements).
 * @param count  Number of samples to read.
 * @return true if all samples were read successfully, false on failure.
 */
bool adc_read_into_buffer(uint16_t *buf, int count);

/**
 * Release the ADC acquired by adc_acquire().
 */
void adc_release(void);

#endif /* ADC_READ_H */
