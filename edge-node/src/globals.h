#ifndef GLOBALS_H
#define GLOBALS_H

#include "freertos/FreeRTOS.h"
#include "freertos/queue.h"
#include "config.h"

#include <stdbool.h>
#include <stdint.h>

/**
 * Queue of scan_result_t structs produced by sensing_task and consumed by
 * network_task.  Defined in main.c; declared extern here for use in both
 * tasks without creating a circular dependency on config.h.
 */
extern QueueHandle_t g_result_queue;

/**
 * FFT spectrum diagnostic buffer.  Sensing task writes g_fft_spectrum[]
 * then sets g_fft_ready = true.  Network task reads the buffer after
 * seeing the flag, then clears it.  The queue post between them acts
 * as a memory barrier.
 *
 * Defined in sensing_task.c.
 */
extern uint8_t       g_fft_spectrum[FFT_BINS];
extern volatile bool g_fft_ready;

#endif /* GLOBALS_H */
