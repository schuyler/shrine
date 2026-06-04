#ifndef ADC_READ_H
#define ADC_READ_H

#include <stdint.h>
#include "esp_err.h"

/**
 * Initialise ADC continuous mode on ADC1_CH0 (GPIO36).
 *
 * Configures adc_continuous_new_handle(), single channel, TYPE1 output
 * format, 220 ksps requested (actual ~180 ksps after I2S 9/11 ratio).
 * Starts conversion and discards the first frame to flush stale DMA data.
 *
 * Must be called once before adc_calibrate_fs() or adc_read_frame().
 */
esp_err_t adc_init(void);

/**
 * Calibrate the actual ADC sample rate by timing DMA burst reads.
 *
 * Flushes 5 frames, then reads CAL_BURST_READS (200) frames and divides
 * total samples by elapsed time.
 *
 * Uses a static internal buffer. Must be called from a single task context
 * during startup; not reentrant.
 *
 * @param fs_out  Output: measured sample rate in Hz.
 * @return ESP_OK on success, ESP_FAIL if no data was received.
 */
esp_err_t adc_calibrate_fs(float *fs_out);

/**
 * Read one DMA frame into buf.
 *
 * Blocks up to timeout_ms waiting for data. On success, *bytes_read
 * contains the number of bytes written to buf (always <= ADC_FRAME_SIZE).
 *
 * buf must be at least ADC_FRAME_SIZE bytes and word-aligned (WORD_ALIGNED_ATTR).
 *
 * @param buf          Destination buffer (WORD_ALIGNED_ATTR uint8_t[ADC_FRAME_SIZE]).
 * @param bytes_read   Output: bytes actually read.
 * @param timeout_ms   Timeout in milliseconds.
 * @return ESP_OK on success, ESP_ERR_TIMEOUT, or other IDF error.
 */
esp_err_t adc_read_frame(uint8_t *buf, uint32_t *bytes_read, uint32_t timeout_ms);

/**
 * Stop ADC continuous conversion and release the handle.
 * Safe to call even if adc_init() was not called.
 */
void adc_stop(void);

#endif /* ADC_READ_H */
