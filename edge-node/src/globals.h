#ifndef GLOBALS_H
#define GLOBALS_H

#include "freertos/FreeRTOS.h"
#include "freertos/queue.h"

/**
 * Queue of scan_result_t structs produced by sensing_task and consumed by
 * network_task.  Defined in main.c; declared extern here for use in both
 * tasks without creating a circular dependency on config.h.
 */
extern QueueHandle_t g_result_queue;

#endif /* GLOBALS_H */
