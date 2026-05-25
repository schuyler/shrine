#ifndef SENSING_TASK_H
#define SENSING_TASK_H

/**
 * FreeRTOS task entry point for the sensing pipeline.
 *
 * Runs on SENSING_TASK_CORE (Core 1) at SENSING_TASK_PRIO.
 *
 * @param param  Pointer to node_config_t (cast from void *).
 *               The pointer must remain valid for the lifetime of the task.
 */
void sensing_task(void *param);

#endif /* SENSING_TASK_H */
