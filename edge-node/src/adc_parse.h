#ifndef ADC_PARSE_H
#define ADC_PARSE_H

#include <stdint.h>

// Parse raw DMA bytes (ESP32 ADC continuous TYPE1 format) into a uint16_t
// sample array. Each DMA entry is 2 bytes (SOC_ADC_DIGI_RESULT_BYTES=2).
// Bits [11:0] = 12-bit ADC data, bits [15:12] = channel.
// Extracts bits [11:0] by mask (no ESP-IDF dependency).
//
// Returns the number of samples written to out[].
// Stops early if max_out is reached.
int adc_parse_frame(const uint8_t *raw, int raw_len,
                    uint16_t *out, int max_out);

// Feed variable-length sample batches into a fixed-size window buffer.
// Manages position tracking across calls. Returns the number of times
// the window was completely filled during this call.
//
// On each fill: copies completed window to snapshot[] (if non-NULL),
// resets *pos to 0, and continues with remaining samples.
//
// window:      destination buffer (window_size elements)
// window_size: number of samples per complete window
// pos:         pointer to current write position (caller-owned state)
// samples:     input sample array
// n_samples:   number of input samples
// snapshot:    if non-NULL, receives a copy of the completed window each time it fills
//              (must have space for window_size elements)
int window_accumulate(uint16_t *window, int window_size, int *pos,
                      const uint16_t *samples, int n_samples,
                      uint16_t *snapshot);

#endif /* ADC_PARSE_H */
