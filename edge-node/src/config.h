#ifndef CONFIG_H
#define CONFIG_H

#include <stdint.h>
#include <stdbool.h>

/* ---------------------------------------------------------------------------
 * Pin definitions
 * -------------------------------------------------------------------------*/

#define PIN_EXCITATION      4   /* LEDC PWM output */
#define PIN_SPI_CLK        12   /* SPI2_HOST clock */
#define PIN_SPI_MISO       13   /* MCP3201 D_out */
#define PIN_SPI_CS         10   /* Software CS */
#define PIN_SYNC            5   /* Sync bus (leader: output, follower: input) */

/* ---------------------------------------------------------------------------
 * TDM / frame timing
 * -------------------------------------------------------------------------*/

#define TDM_SLOTS          10
#define TDM_SLOT_US      1000   /* 1 ms per slot */
#define TDM_FRAME_MS       10   /* 10 ms total frame */
#define SETTLE_US         250
#define INTEGRATE_US      750
#define SAMPLES_PER_CYCLE    5
#define SYNC_TIMEOUT_MS    15

/* ---------------------------------------------------------------------------
 * SPI
 * -------------------------------------------------------------------------*/

#define SPI_CLOCK_HZ    1000000 /* 1 MHz */

/* ---------------------------------------------------------------------------
 * Task configuration
 * -------------------------------------------------------------------------*/

#define SENSING_TASK_CORE     1
#define SENSING_TASK_PRIO    20
#define SENSING_TASK_STACK 4096
#define NETWORK_TASK_CORE     0
#define NETWORK_TASK_PRIO     5
#define NETWORK_TASK_STACK 8192
#define RESULT_QUEUE_DEPTH    4

/* ---------------------------------------------------------------------------
 * Data structures
 * -------------------------------------------------------------------------*/

typedef struct {
    uint8_t  node_id;
    bool     is_leader;
    char     wifi_ssid[33];
    char     wifi_pass[65];
    char     osc_host[16];
    uint16_t osc_port;
} node_config_t;

typedef struct {
    float self_cap_mag;
    float gsr_mag[3];
    float gsr_phase[3];
} scan_result_t;

#endif /* CONFIG_H */
