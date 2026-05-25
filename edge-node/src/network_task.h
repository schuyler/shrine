#ifndef NETWORK_TASK_H
#define NETWORK_TASK_H

/**
 * FreeRTOS task entry point for WiFi + OSC output.
 *
 * Runs on NETWORK_TASK_CORE (Core 0) at NETWORK_TASK_PRIO.
 *
 * @param param  Pointer to node_config_t (cast from void *).
 *               The pointer must remain valid for the lifetime of the task.
 */
void network_task(void *param);

#endif /* NETWORK_TASK_H */
