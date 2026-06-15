/* sensing_task.c — FDM capacitive sensing loop.
 *
 * Calibrates ADC sample rate via DMA burst timing, starts LEDC excitation at
 * this node's carrier frequency, then runs a continuous demodulation loop:
 * accumulate DMA frames into a window, compute self-stdev and I/Q magnitudes
 * at all 4 carrier bins, post a scan_result_t to g_result_queue for
 * network_task.
 */

#include "sensing_task.h"
#include "config.h"
#include "excitation.h"
#include "adc_read.h"
#include "adc_parse.h"
#include "fdm_math.h"

#include "freertos/FreeRTOS.h"
#include "freertos/queue.h"
#include "esp_attr.h"
#include "esp_log.h"
#include <math.h>   /* cosf, sinf */

/* g_result_queue is declared in globals.h and defined in main.c */
#include "globals.h"

static const char *TAG = "sensing";

/* Enforce single-fill-per-frame: one DMA frame (ADC_FRAME_SIZE/2 samples) must
 * be smaller than one window (WINDOW_N_DEFAULT samples).  If this were violated,
 * window_accumulate could return fills > 1 and intermediate windows would be
 * overwritten in s_snapshot_buf before being processed.
 */
_Static_assert((FFT_N & (FFT_N - 1)) == 0,
               "FFT_N must be a power of 2 for radix-2 FFT");

_Static_assert(ADC_FRAME_SIZE / 2 < WINDOW_N_DEFAULT,
               "DMA frame must contain fewer samples than one window to avoid "
               "dropping intermediate windows in the sensing loop");

/* DMA receive buffer — must be word-aligned for DMA */
static WORD_ALIGNED_ATTR uint8_t s_dma_buf[ADC_FRAME_SIZE];

/* Rolling window accumulation buffer */
static uint16_t s_window_buf[WINDOW_N_DEFAULT];
static int s_window_pos = 0;

/* Snapshot of last completed window — processed after window_accumulate fills */
static uint16_t s_snapshot_buf[WINDOW_N_DEFAULT];

/* Parsed samples extracted from one DMA frame */
static uint16_t s_frame_samples[ADC_FRAME_SIZE / 2];  /* max samples per frame */

/* FFT diagnostic buffers */
static float s_fft_buf[FFT_N * 2];          /* 16 KB, interleaved complex */
static float s_hann[WINDOW_N_DEFAULT];       /* Hann window coefficients */

/* FFT shared state (declared extern in globals.h) */
uint8_t       g_fft_spectrum[FFT_BINS];
volatile bool g_fft_ready = false;

/* -------------------------------------------------------------------------
 * sensing_task
 * -------------------------------------------------------------------------*/

void sensing_task(void *param)
{
    node_config_t *cfg = (node_config_t *)param;

    ESP_LOGI(TAG, "starting on node %u", cfg->node_id);

    /* --- Startup: calibrate sample rate via DMA burst timing ----------- */
    float fs;
    esp_err_t cal_err = adc_calibrate_fs(&fs);
    if (cal_err != ESP_OK) {
        ESP_LOGE(TAG, "ADC calibration failed — restarting");
        esp_restart();
    }
    uint32_t sample_rate = (uint32_t)fs;

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

    /* --- Startup: precompute Hann window -------------------------------- */
    fdm_hann_window(s_hann, N);

    int fft_counter = 0;

    /* -------------------------------------------------------------------- */
    /* Main sensing loop                                                     */
    /* -------------------------------------------------------------------- */
    while (1) {
        /* Read one DMA frame */
        uint32_t bytes_read = 0;
        esp_err_t err = adc_read_frame(s_dma_buf, &bytes_read, 1000);
        if (err != ESP_OK || bytes_read == 0) {
            ESP_LOGE(TAG, "adc_read_frame failed: %s", esp_err_to_name(err));
            continue;
        }

        /* Extract 12-bit samples from the TYPE1 DMA frame */
        int n_samples = adc_parse_frame(s_dma_buf, (int)bytes_read,
                                        s_frame_samples,
                                        (int)(sizeof(s_frame_samples) / sizeof(s_frame_samples[0])));
        if (n_samples <= 0) {
            continue;
        }

        /* Accumulate into rolling window; snapshot is copied when window fills */
        int fills = window_accumulate(s_window_buf, (int)N, &s_window_pos,
                                      s_frame_samples, n_samples,
                                      s_snapshot_buf);

        /* fills is always 0 or 1 given the _Static_assert above */
        if (fills <= 0) {
            /* Window not yet full — keep accumulating */
            continue;
        }

        /* Process the most recently completed window snapshot */

        /* Stdev (DC-removed, self-presence metric) */
        result.self_stdev = fdm_stdev(s_snapshot_buf, N);

        /* I/Q demodulation at all 4 carriers */
        float mag[NUM_NODES];
        for (int c = 0; c < NUM_NODES; c++) {
            mag[c] = fdm_demod_magnitude(s_snapshot_buf, N,
                                         nco_cos_step[c], nco_sin_step[c]);
        }

        /* Extract self-carrier magnitude */
        result.self_carrier_mag = mag[cfg->node_id];

        /* Assign GSR magnitudes in gsr_node order */
        for (int offset = 1; offset <= 3; offset++) {
            int j = (cfg->node_id + offset) % NUM_NODES;
            result.gsr_mag[offset - 1] = mag[j];
        }

        /* --- FFT spectrum diagnostic (every FFT_INTERVAL_WINDOWS windows) ---
         * Computed BEFORE xQueueSend so that the queue post's memory barrier
         * guarantees the spectrum buffer is visible to the network task. */
        if (++fft_counter >= FFT_INTERVAL_WINDOWS) {
            fft_counter = 0;

            /* DC-remove, apply Hann window, zero-pad to FFT_N */
            float sum = 0.0f;
            for (int i = 0; i < N; i++) sum += (float)s_snapshot_buf[i];
            float fft_mean = sum / (float)N;

            int fft_fill = (N < FFT_N) ? N : FFT_N;
            for (int i = 0; i < fft_fill; i++) {
                s_fft_buf[2*i]     = ((float)s_snapshot_buf[i] - fft_mean) * s_hann[i];
                s_fft_buf[2*i + 1] = 0.0f;  /* imaginary = 0 */
            }
            /* Zero-pad remaining samples to FFT_N */
            for (int i = fft_fill; i < FFT_N; i++) {
                s_fft_buf[2*i]     = 0.0f;
                s_fft_buf[2*i + 1] = 0.0f;
            }

            fdm_fft_radix2(s_fft_buf, FFT_N);
            fdm_fft_log_magnitudes(s_fft_buf, FFT_N, g_fft_spectrum);
            g_fft_ready = true;
        }

        /* Post result to the network task (non-blocking: drop if full).
         * The queue post provides a memory barrier that makes g_fft_spectrum
         * writes (above) visible to the network task on the other core. */
        if (xQueueSend(g_result_queue, &result, 0) != pdTRUE) {
            ESP_LOGD(TAG, "result queue full — window dropped");
        }
    } /* while(1) */
}
