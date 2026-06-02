/* sensing_task.c — FDM capacitive sensing loop.
 *
 * Acquires the SPI bus, calibrates sample rate, starts LEDC excitation at
 * this node's carrier frequency, then runs a continuous demodulation loop:
 * collect one window of ADC samples, compute self-stdev and I/Q magnitudes
 * at all 4 carrier bins, post a scan_result_t to g_result_queue for
 * network_task.
 */

#include "sensing_task.h"
#include "config.h"
#include "excitation.h"
#include "adc_read.h"
#include "fdm_math.h"

#include "freertos/FreeRTOS.h"
#include "freertos/queue.h"
#include "esp_log.h"
#include "esp_timer.h"
#include <math.h>   /* cosf, sinf, sqrtf */

/* g_result_queue is declared in globals.h and defined in main.c */
#include "globals.h"

static const char *TAG = "sensing";

/* -------------------------------------------------------------------------
 * Sample count for calibration pass.  More samples → more accurate rate
 * estimate, at the cost of a longer startup delay (~10 ms at 1 MHz SPI).
 */
#define CALIB_SAMPLES 500

/* -------------------------------------------------------------------------
 * Calibration: measure actual ADC sample rate.
 * Called inside an already-acquired SPI bus — no internal acquire/release.
 * -------------------------------------------------------------------------*/

static uint32_t calibrate_sample_rate(void)
{
    uint16_t buf[CALIB_SAMPLES];

    int64_t t0 = esp_timer_get_time();   /* µs */
    bool calib_ok = adc_read_into_buffer(buf, CALIB_SAMPLES);
    int64_t t1 = esp_timer_get_time();

    if (!calib_ok) {
        ESP_LOGW(TAG, "calibration: SPI errors during sampling — "
                 "rate estimate may be unreliable");
    }

    int64_t elapsed_us = t1 - t0;
    if (elapsed_us <= 0) {
        ESP_LOGW(TAG, "calibration elapsed_us=%lld, using default 100000 Hz",
                 elapsed_us);
        return 100000;
    }

    /* samples_per_second = CALIB_SAMPLES / (elapsed_us / 1e6) */
    uint32_t sample_rate = (uint32_t)(((int64_t)CALIB_SAMPLES * 1000000LL)
                                      / elapsed_us);

    ESP_LOGI(TAG, "calibration: %d samples in %lld µs → sample_rate=%lu Hz",
             CALIB_SAMPLES, elapsed_us, sample_rate);

    return sample_rate;
}

/* -------------------------------------------------------------------------
 * sensing_task
 * -------------------------------------------------------------------------*/

void sensing_task(void *param)
{
    node_config_t *cfg = (node_config_t *)param;

    ESP_LOGI(TAG, "starting on node %u", cfg->node_id);

    /* --- Startup: acquire SPI bus for entire run ----------------------- */
    adc_acquire();

    /* --- Startup: calibrate sample rate (runs inside acquired bus) ----- */
    uint32_t sample_rate = calibrate_sample_rate();

    /* --- Startup: clamp window_n to static buffer size ----------------- */
    uint16_t N = cfg->window_n;
    if (N > WINDOW_N_DEFAULT) {
        ESP_LOGW(TAG, "window_n=%u clamped to WINDOW_N_DEFAULT=%u",
                 N, WINDOW_N_DEFAULT);
        N = WINDOW_N_DEFAULT;
    }

    /* --- Startup: compute this node's carrier bin and excitation freq -- */
    uint16_t k_self = cfg->base_k + cfg->node_id * cfg->step_k;
    uint32_t f_exc  = (uint32_t)((uint64_t)k_self * sample_rate / N);

    ESP_LOGI(TAG, "node_id=%u k_self=%u sample_rate=%lu f_exc=%lu Hz N=%u",
             cfg->node_id, k_self, sample_rate, f_exc, N);

    excitation_start(f_exc);

    /* --- Startup: precompute NCO step phasors for all 4 carriers ------- */
    float nco_cos_step[NUM_NODES];
    float nco_sin_step[NUM_NODES];
    for (int j = 0; j < NUM_NODES; j++) {
        uint16_t k = cfg->base_k + (uint16_t)j * cfg->step_k;
        float angle = 2.0f * (float)M_PI * k / N;
        nco_cos_step[j] =  cosf(angle);
        nco_sin_step[j] = -sinf(angle);  /* negative: e^{-jωn} DFT convention */
    }

    /* --- Startup: fill gsr_node ordering ------------------------------- */
    scan_result_t result;
    fdm_gsr_ordering(cfg->node_id, NUM_NODES, result.gsr_node);
    result.node_id = cfg->node_id;

    /* Static sample buffer (not stack-allocated) */
    static uint16_t buf[WINDOW_N_DEFAULT];

    /* -------------------------------------------------------------------- */
    /* Main sensing loop                                                     */
    /* -------------------------------------------------------------------- */
    while (1) {
        /* Fill one complete window */
        bool ok = adc_read_into_buffer(buf, N);
        if (!ok) {
            ESP_LOGW(TAG, "adc_read_into_buffer failed — skipping window");
            continue;
        }

        /* Stdev (DC-removed, self-presence metric) */
        result.self_stdev = fdm_stdev(buf, N);

        /* I/Q demodulation at all 4 carriers */
        float mag[NUM_NODES];
        for (int c = 0; c < NUM_NODES; c++) {
            mag[c] = fdm_demod_magnitude(buf, N, nco_cos_step[c], nco_sin_step[c]);
        }

        /* Extract self-carrier magnitude */
        result.self_carrier_mag = mag[cfg->node_id];

        /* Assign GSR magnitudes in gsr_node order */
        for (int offset = 1; offset <= 3; offset++) {
            int j = (cfg->node_id + offset) % NUM_NODES;
            result.gsr_mag[offset - 1] = mag[j];
        }

        /* Post result to the network task (non-blocking: drop if full) */
        if (xQueueSend(g_result_queue, &result, 0) != pdTRUE) {
            ESP_LOGD(TAG, "result queue full — window dropped");
        }
    } /* while(1) */
}
