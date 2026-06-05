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

    cal->scale[0] = cfg->scale_stdev / 1000.0f;
    cal->scale[1] = cfg->scale_gsr0  / 1000.0f;
    cal->scale[2] = cfg->scale_gsr1  / 1000.0f;
    cal->scale[3] = cfg->scale_gsr2  / 1000.0f;

    ESP_LOGI(TAG, "floors: stdev=%.0f gsr=[%.0f, %.0f, %.0f]",
             cal->floor[0], cal->floor[1], cal->floor[2], cal->floor[3]);
    ESP_LOGI(TAG, "scales: stdev=%.3f gsr=[%.3f, %.3f, %.3f]",
             cal->scale[0], cal->scale[1], cal->scale[2], cal->scale[3]);
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
        out[i] = fmaxf(0.0f, vals[i] - cal->floor[i]) * cal->scale[i];
    }

    *carrier_mag = raw->self_carrier_mag;
}
