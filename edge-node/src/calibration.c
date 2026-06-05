#include "calibration.h"

#include <math.h>
#include <string.h>
#include "esp_log.h"

static const char *TAG = "calibration";

void calibration_init(cal_state_t *cal, const node_config_t *cfg)
{
    memset(cal, 0, sizeof(*cal));
    cal->initialized = false;

    cal->scale[0] = cfg->scale_stdev / 1000.0f;
    cal->scale[1] = cfg->scale_gsr0  / 1000.0f;
    cal->scale[2] = cfg->scale_gsr1  / 1000.0f;
    cal->scale[3] = cfg->scale_gsr2  / 1000.0f;

    ESP_LOGI(TAG, "scale factors: stdev=%.3f gsr0=%.3f gsr1=%.3f gsr2=%.3f",
             cal->scale[0], cal->scale[1], cal->scale[2], cal->scale[3]);
}

void calibration_apply(cal_state_t *cal, const scan_result_t *raw,
                       float *out, float *carrier_mag)
{
#if !CAL_ENABLED
    /* Passthrough: no floor subtraction or scaling. */
    out[0] = raw->self_stdev;
    out[1] = raw->gsr_mag[0];
    out[2] = raw->gsr_mag[1];
    out[3] = raw->gsr_mag[2];
    *carrier_mag = raw->self_carrier_mag;
    return;
#endif

    /* Extract the 4 calibrated channels from the scan result. */
    float vals[CAL_NUM_CHANNELS] = {
        raw->self_stdev,
        raw->gsr_mag[0],
        raw->gsr_mag[1],
        raw->gsr_mag[2],
    };

    /* First observation: seed EMA and floor from raw values. */
    if (!cal->initialized) {
        for (int i = 0; i < CAL_NUM_CHANNELS; i++) {
            cal->ema[i]     = vals[i];
            cal->ema_var[i] = 0.0f;
            cal->floor[i]   = vals[i];
        }
        cal->quiet_count = 0;
        cal->obs_count   = 0;
        cal->initialized = true;
        ESP_LOGI(TAG, "initialized floors: stdev=%.1f gsr=[%.1f, %.1f, %.1f]",
                 cal->floor[0], cal->floor[1], cal->floor[2], cal->floor[3]);
    }

    /* Update EMA and EMA variance for all channels. */
    for (int i = 0; i < CAL_NUM_CHANNELS; i++) {
        cal->ema[i] = CAL_EMA_ALPHA * vals[i]
                     + (1.0f - CAL_EMA_ALPHA) * cal->ema[i];
        float dev = vals[i] - cal->ema[i];
        cal->ema_var[i] = CAL_EMA_ALPHA * (dev * dev)
                        + (1.0f - CAL_EMA_ALPHA) * cal->ema_var[i];
    }

    /* Count observations; cap to avoid overflow. */
    if (cal->obs_count < CAL_WARMUP) {
        cal->obs_count++;
    }

    /* Quiescence detection on self_stdev (channel 0).
     * Gated on warmup to let EMA variance converge before trusting it. */
    float ema_sd = sqrtf(cal->ema_var[0]);
    bool quiet = (cal->obs_count >= CAL_WARMUP)
              && (ema_sd < CAL_QUIET_SD_THRESH)
              && (cal->ema[0] < CAL_QUIET_LEVEL_THRESH);

    if (quiet) {
        cal->quiet_count++;
        if (cal->quiet_count == CAL_QUIET_SETTLE) {
            /* Snap all floors to current EMA. */
            ESP_LOGI(TAG, "floor update: stdev %.1f→%.1f  gsr [%.1f→%.1f, %.1f→%.1f, %.1f→%.1f]",
                     cal->floor[0], cal->ema[0],
                     cal->floor[1], cal->ema[1],
                     cal->floor[2], cal->ema[2],
                     cal->floor[3], cal->ema[3]);
            for (int i = 0; i < CAL_NUM_CHANNELS; i++) {
                cal->floor[i] = cal->ema[i];
            }
            /* Re-arm: allow floor to track drift during sustained quiescence. */
            cal->quiet_count = 0;
        }
    } else {
        cal->quiet_count = 0;
    }

    /* Apply floor subtraction and scale. */
    for (int i = 0; i < CAL_NUM_CHANNELS; i++) {
        out[i] = fmaxf(0.0f, vals[i] - cal->floor[i]) * cal->scale[i];
    }

    /* carrier_mag passes through unchanged. */
    *carrier_mag = raw->self_carrier_mag;
}
