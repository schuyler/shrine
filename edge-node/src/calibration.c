#include "calibration.h"

#include <math.h>
#include <string.h>
#include "esp_log.h"

static const char *TAG = "calibration";

void calibration_init(cal_state_t *cal, const node_config_t *cfg)
{
    memset(cal, 0, sizeof(*cal));

    cal->floor[0] = (float)cfg->floor_stdev;
    cal->floor[1] = (float)cfg->floor_gsr0;
    cal->floor[2] = (float)cfg->floor_gsr1;
    cal->floor[3] = (float)cfg->floor_gsr2;

    cal->ceiling[0] = (float)cfg->ceil_stdev;
    cal->ceiling[1] = (float)cfg->ceil_gsr0;
    cal->ceiling[2] = (float)cfg->ceil_gsr1;
    cal->ceiling[3] = (float)cfg->ceil_gsr2;

    static const char * const ch_names[CAL_NUM_CHANNELS] __attribute__((unused)) = {
        "stdev", "gsr0", "gsr1", "gsr2"
    };

    for (int i = 0; i < CAL_NUM_CHANNELS; i++) {
        if (cal->ceiling[i] == 65535.0f || cal->ceiling[i] <= cal->floor[i]) {
            cal->unconfigured[i] = true;
            ESP_LOGW(TAG, "channel %s unconfigured (floor=%.0f ceiling=%.0f)",
                     ch_names[i], cal->floor[i], cal->ceiling[i]);
        } else {
            cal->unconfigured[i] = false;
        }
    }

    ESP_LOGI(TAG, "floors:   stdev=%.0f gsr=[%.0f, %.0f, %.0f]",
             cal->floor[0], cal->floor[1], cal->floor[2], cal->floor[3]);
    ESP_LOGI(TAG, "ceilings: stdev=%.0f gsr=[%.0f, %.0f, %.0f]",
             cal->ceiling[0], cal->ceiling[1], cal->ceiling[2], cal->ceiling[3]);
    ESP_LOGI(TAG, "ranges:   stdev=%.0f gsr=[%.0f, %.0f, %.0f]",
             cal->ceiling[0] - cal->floor[0],
             cal->ceiling[1] - cal->floor[1],
             cal->ceiling[2] - cal->floor[2],
             cal->ceiling[3] - cal->floor[3]);
}

void calibration_apply(const cal_state_t *cal, const scan_result_t *raw,
                       float *out, float *carrier_mag)
{
#if !CAL_ENABLED
    out[0] = raw->self_stdev;
    out[1] = raw->gsr_mag[0];
    out[2] = raw->gsr_mag[1];
    out[3] = raw->gsr_mag[2];
    *carrier_mag = raw->self_carrier_mag;
    return;
#endif

    float vals[CAL_NUM_CHANNELS] = {
        raw->self_stdev,
        raw->gsr_mag[0],
        raw->gsr_mag[1],
        raw->gsr_mag[2],
    };

    for (int i = 0; i < CAL_NUM_CHANNELS; i++) {
        if (cal->unconfigured[i]) {
            out[i] = 0.0f;
        } else {
            out[i] = fminf(1.0f, fmaxf(0.0f,
                (vals[i] - cal->floor[i]) / (cal->ceiling[i] - cal->floor[i])));
        }
    }

    *carrier_mag = raw->self_carrier_mag;
}
