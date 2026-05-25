#include "sensing_task.h"
#include "config.h"
#include "sync.h"
#include "tdm.h"
#include "excitation.h"
#include "adc_read.h"

#include "freertos/FreeRTOS.h"
#include "freertos/queue.h"
#include "freertos/semphr.h"
#include "esp_log.h"
#include "esp_timer.h"
#include "esp_rom_sys.h"   /* esp_rom_delay_us */
#include <math.h>          /* nanf */

/* g_result_queue is declared in globals.h and defined in main.c */
#include "globals.h"

static const char *TAG = "sensing";

/* -------------------------------------------------------------------------
 * Sample count for calibration pass.  More samples → more accurate rate
 * estimate, at the cost of a longer startup delay (~10 ms at 1 MHz SPI).
 */
#define CALIB_SAMPLES 500

/* -------------------------------------------------------------------------
 * Calibration: measure actual ADC sample rate and derive excitation freq.
 * -------------------------------------------------------------------------*/

static uint32_t calibrate_sample_rate(uint32_t *out_excit_freq)
{
    uint16_t buf[CALIB_SAMPLES];

    adc_acquire();
    int64_t t0 = esp_timer_get_time();   /* µs */
    bool calib_ok = adc_read_into_buffer(buf, CALIB_SAMPLES);
    int64_t t1 = esp_timer_get_time();
    adc_release();

    if (!calib_ok) {
        ESP_LOGW(TAG, "calibration: SPI errors during sampling — "
                 "rate estimate may be unreliable");
    }

    int64_t elapsed_us = t1 - t0;
    if (elapsed_us <= 0) {
        ESP_LOGW(TAG, "calibration elapsed_us=%lld, using default 10000 Hz",
                 elapsed_us);
        *out_excit_freq = 10000 / SAMPLES_PER_CYCLE;
        return 10000;
    }

    /* samples_per_second = CALIB_SAMPLES / (elapsed_us / 1e6) */
    uint32_t sample_rate = (uint32_t)(((int64_t)CALIB_SAMPLES * 1000000LL)
                                      / elapsed_us);
    *out_excit_freq = sample_rate / SAMPLES_PER_CYCLE;

    ESP_LOGI(TAG,
             "calibration: %d samples in %lld µs → sample_rate=%lu Hz, "
             "excit_freq=%lu Hz",
             CALIB_SAMPLES, elapsed_us, sample_rate, *out_excit_freq);

    return sample_rate;
}

/* -------------------------------------------------------------------------
 * sensing_task
 * -------------------------------------------------------------------------*/

void sensing_task(void *param)
{
    node_config_t *cfg = (node_config_t *)param;

    ESP_LOGI(TAG, "starting on node %u (%s)",
             cfg->node_id, cfg->is_leader ? "leader" : "follower");

    /* --- Startup: calibrate sample rate --------------------------------- */
    uint32_t excit_freq;
    uint32_t sample_rate = calibrate_sample_rate(&excit_freq);

    /* --- Startup: precompute GSR mapping -------------------------------- */
    tdm_init_gsr_mapping(cfg->node_id);

    const tdm_slot_t *schedule = tdm_get_schedule();

    /* Buffer large enough for one slot's worth of samples.
     * At ~100 kHz sample rate and 750 µs integration window: ~75 samples.
     * 256 gives comfortable headroom. */
    uint16_t sample_buf[256];

    /* -------------------------------------------------------------------- */
    /* Main sensing loop                                                     */
    /* -------------------------------------------------------------------- */
    while (1) {
        /* Wait for the frame-sync semaphore. */
        if (xSemaphoreTake(g_sync_sem,
                           pdMS_TO_TICKS(SYNC_TIMEOUT_MS)) != pdTRUE) {
            ESP_LOGW(TAG, "sync timeout — waiting for next frame");
            continue;
        }

        scan_result_t result = { 0 };

        /* ---------------------------------------------------------------- */
        /* Iterate over all 10 TDM slots                                    */
        /* ---------------------------------------------------------------- */
        for (int slot = 0; slot < TDM_SLOTS; slot++) {
            const tdm_slot_t *s = &schedule[slot];

            bool am_tx = (s->tx_node == cfg->node_id);
            bool am_rx = (s->rx_node == cfg->node_id);

            int64_t slot_start = esp_timer_get_time();

            /* ---- TX role ----------------------------------------------- */
            if (am_tx) {
                excitation_start(excit_freq);
            }

            /* ---- RX role ----------------------------------------------- */
            if (am_rx) {
                /* Let the excitation settle before integrating. */
                esp_rom_delay_us(SETTLE_US);

                /* Compute how many samples fit in the integration window at
                 * the calibrated rate.  Clamp to buffer size. */
                int n_samples = (int)(((uint64_t)sample_rate * INTEGRATE_US)
                                      / 1000000ULL);
                if (n_samples < 1)  n_samples = 1;
                if (n_samples > (int)(sizeof(sample_buf) / sizeof(sample_buf[0])))
                    n_samples = (int)(sizeof(sample_buf) / sizeof(sample_buf[0]));

                adc_acquire();
                bool adc_ok = adc_read_into_buffer(sample_buf, n_samples);
                adc_release();

                if (!adc_ok) {
                    /* SPI error: record NaN and skip demodulation. */
                    if (!s->is_gsr) {
                        result.self_cap_mag = nanf("");
                    } else {
                        int gsr_idx = tdm_gsr_result_index((uint8_t)slot);
                        if (gsr_idx >= 0 && gsr_idx < 3) {
                            result.gsr_mag[gsr_idx]   = nanf("");
                            result.gsr_phase[gsr_idx] = nanf("");
                        }
                    }
                } else {
                    float mag, phase;
                    tdm_demod_iq(sample_buf, n_samples, &mag, &phase);

                    if (!s->is_gsr) {
                        /* Self-cap slot: tx == rx == node_id */
                        result.self_cap_mag = mag;
                    } else {
                        int gsr_idx = tdm_gsr_result_index((uint8_t)slot);
                        if (gsr_idx >= 0 && gsr_idx < 3) {
                            result.gsr_mag[gsr_idx]   = mag;
                            result.gsr_phase[gsr_idx] = phase;
                        }
                    }
                }
            }

            /* ---- Pad remainder of slot to TDM_SLOT_US ----------------- */
            /* Must pad BEFORE stopping excitation so that a remote RX node
             * (GSR TX-only case) sees excitation for the full slot duration.
             * In the self-cap case (am_tx && am_rx) this node is both TX and
             * RX, so RX work is already done before we reach this point —
             * padding then stopping is still correct.  In the idle case
             * (!am_tx && !am_rx) neither branch runs, so we just pad. */
            int64_t elapsed = esp_timer_get_time() - slot_start;
            int64_t remaining = (int64_t)TDM_SLOT_US - elapsed;
            if (remaining > 0) {
                esp_rom_delay_us((uint32_t)remaining);
            }

            /* ---- Slot-end housekeeping --------------------------------- */
            if (am_tx) {
                excitation_stop();
            }
        } /* for each slot */

        /* Post result to the network task (non-blocking: drop if full). */
        if (xQueueSend(g_result_queue, &result, 0) != pdTRUE) {
            ESP_LOGD(TAG, "result queue full — frame dropped");
        }
    } /* while(1) */
}
