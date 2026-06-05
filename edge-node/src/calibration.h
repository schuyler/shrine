#ifndef CALIBRATION_H
#define CALIBRATION_H

#include "config.h"

/* Set to 0 to disable calibration (pass raw values through) */
#ifndef CAL_ENABLED
#define CAL_ENABLED         1
#endif

/* Number of calibrated channels: self_stdev + gsr_mag[0..2] */
#define CAL_NUM_CHANNELS    4

typedef struct {
    float floor[CAL_NUM_CHANNELS];
    float scale[CAL_NUM_CHANNELS];
} cal_state_t;

/**
 * Initialize calibration state from NVS config (floor + scale per channel).
 */
void calibration_init(cal_state_t *cal, const node_config_t *cfg);

/**
 * Apply calibration: out[ch] = max(0, raw - floor) * scale.
 * carrier_mag passes through unchanged.
 */
void calibration_apply(const cal_state_t *cal, const scan_result_t *raw,
                       float *out, float *carrier_mag);

#endif /* CALIBRATION_H */
