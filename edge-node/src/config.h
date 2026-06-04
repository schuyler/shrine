#ifndef CONFIG_H
#define CONFIG_H

#include <stdint.h>

/* ---------------------------------------------------------------------------
 * Pin definitions
 * -------------------------------------------------------------------------*/

#define PIN_EXCITATION      4           /* LEDC PWM output */
#define PIN_ADC             GPIO_NUM_36 /* ADC1_CH0 on ESP32-WROOM-32 */

/* ---------------------------------------------------------------------------
 * ADC continuous mode (ESP32-WROOM-32 internal ADC via DMA)
 * -------------------------------------------------------------------------*/

#define ADC_SAMPLE_RATE     220000  /* requested; actual ~180 ksps (I2S 9/11 ratio) */
#define ADC_FRAME_SIZE      2048    /* DMA frame size in bytes; 1024 samples x 2 bytes */
#define ADC_POOL_SIZE       8192    /* DMA ring buffer size in bytes */

/* ---------------------------------------------------------------------------
 * FDM window and carrier parameters
 * -------------------------------------------------------------------------*/

#define WINDOW_N_DEFAULT    1800    /* samples per demod window */
#define BASE_K_DEFAULT       180    /* DFT bin for node 0 */
#define STEP_K_DEFAULT        20    /* bin spacing between nodes */
#define NUM_NODES               4
#define NCO_RENORM_INTERVAL    64   /* informational — fdm_math.c hardcodes this */

/* ---------------------------------------------------------------------------
 * Task configuration
 * -------------------------------------------------------------------------*/

#define SENSING_TASK_CORE     1
#define SENSING_TASK_PRIO    20
#define SENSING_TASK_STACK 4096  /* sample buffer is static, not stack-allocated */
#define NETWORK_TASK_CORE     0
#define NETWORK_TASK_PRIO     5
#define NETWORK_TASK_STACK 8192
#define RESULT_QUEUE_DEPTH    4

/* ---------------------------------------------------------------------------
 * Data structures
 * -------------------------------------------------------------------------*/

typedef struct {
    uint8_t  node_id;
    char     wifi_ssid[33];
    char     wifi_pass[65];
    char     osc_host[16];
    uint16_t osc_port;
    uint16_t base_k;        /* DFT bin for node 0 (NVS optional, default 180) */
    uint16_t step_k;        /* bin spacing (NVS optional, default 20) */
    uint16_t window_n;      /* samples per window (NVS optional, default 1800) */
} node_config_t;

typedef struct {
    float   self_stdev;         /* stdev of DC-removed window (self-presence) */
    float   self_carrier_mag;   /* I/Q magnitude at this node's own carrier */
    float   gsr_mag[3];         /* I/Q magnitude at 3 other carriers */
    uint8_t gsr_node[3];        /* node IDs corresponding to gsr_mag[] */
    uint8_t node_id;            /* this node's ID (for network_task) */
} scan_result_t;

#endif /* CONFIG_H */
