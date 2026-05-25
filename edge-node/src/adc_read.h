#ifndef ADC_READ_H
#define ADC_READ_H

#include <stdint.h>
#include <stdbool.h>
#include "esp_err.h"

/**
 * Initialise SPI2_HOST bus and add the MCP3201 device.
 *
 * Pins are taken from config.h (PIN_SPI_CLK, PIN_SPI_MISO, PIN_SPI_CS).
 * No MOSI line is used (MCP3201 is read-only).
 * Clock: SPI_CLOCK_HZ (1 MHz), mode 0.
 */
esp_err_t adc_init(void);

/**
 * Acquire exclusive ownership of the SPI bus for tight-loop polling.
 * Must be called before adc_read_sample() / adc_read_into_buffer().
 */
void adc_acquire(void);

/**
 * Perform a single SPI transaction and return the 12-bit ADC value.
 *
 * Reads a 16-bit frame from the MCP3201 and extracts bits [13:2]
 * (formula: (raw >> 2) & 0x0FFF).
 *
 * Must be called between adc_acquire() and adc_release().
 *
 * @return 12-bit sample value (0–4095).
 */
uint16_t adc_read_sample(void);

/**
 * Fill buf with count 12-bit samples via a tight polling loop.
 *
 * Must be called between adc_acquire() and adc_release().
 *
 * @param buf    Destination array (must hold at least count elements).
 * @param count  Number of samples to read.
 * @return true if all samples were read successfully, false if any SPI
 *         transaction failed (the buffer contents are indeterminate on false).
 */
bool adc_read_into_buffer(uint16_t *buf, int count);

/**
 * Release the SPI bus acquired by adc_acquire().
 */
void adc_release(void);

#endif /* ADC_READ_H */
