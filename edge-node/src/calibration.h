#ifndef CALIBRATION_H
#define CALIBRATION_H

#include "config.h"
#include <stdbool.h>

/* Set to 0 to disable calibration (pass raw values through) */
#ifndef CAL_ENABLED
#define CAL_ENABLED         1
#endif

/* Number of calibrated channels: self_stdev + gsr_mag[0..2] */
#define CAL_NUM_CHANNELS    4

/* EMA smoothing factor — ~50-window time constant at ~100 windows/sec */
#define CAL_EMA_ALPHA           0.02f

/* Quiescence: EMA stddev of self_stdev must be below this */
#define CAL_QUIET_SD_THRESH     5.0f

/* Quiescence: EMA of self_stdev must be below this absolute ceiling */
#define CAL_QUIET_LEVEL_THRESH  500.0f

/* Consecutive quiet windows before floor update (~2s at 100 Hz) */
#define CAL_QUIET_SETTLE        200

/* Minimum observations before quiescence detection is armed */
#define CAL_WARMUP              200

/* NVS scale factor default: 1000 = 1.0× */
#define CAL_SCALE_DEFAULT       1000

typedef struct {
    float floor[CAL_NUM_CHANNELS];
    float ema[CAL_NUM_CHANNELS];
    float ema_var[CAL_NUM_CHANNELS];
    float scale[CAL_NUM_CHANNELS];
    int   quiet_count;
    int   obs_count;            /* total observations since init */
    bool  initialized;
} cal_state_t;

/**
 * Initialize calibration state.  Loads scale factors from node config.
 * Floor tracking begins on first call to calibration_apply().
 */
void calibration_init(cal_state_t *cal, const node_config_t *cfg);

/**
 * Feed a raw scan result, update floor tracker, produce calibrated output.
 *
 * out[0..3] = max(0, raw − floor) × scale  for self_stdev, gsr_mag[0..2].
 * *carrier_mag = raw self_carrier_mag (unchanged).
 */
void calibration_apply(cal_state_t *cal, const scan_result_t *raw,
                       float *out, float *carrier_mag);

#endif /* CALIBRATION_H */
