/**
 * test_calibration.c — Host-side unit tests for the calibration module.
 *
 * Compiled and run on the host (not on the ESP32).  No IDF dependencies.
 *
 * Test harness: test_utils.h (minimal, provided separately).
 *   TEST_ASSERT(cond)
 *   TEST_ASSERT_FLOAT_NEAR(a, b, tol)
 *   TEST_ASSERT_INT_EQ(a, b)
 *   RUN_TEST(func)
 *   TEST_REPORT()  → returns 0 on all-pass
 *
 * These tests target the NEW floor/ceiling interface (not the old floor/scale).
 * They will not compile until cal_state_t and node_config_t are updated.
 */

#include "test_utils.h"
#include "../src/calibration.h"

#include <stdbool.h>

/* =========================================================================
 * Helpers: build a minimal cal_state_t and scan_result_t for testing
 * ========================================================================= */

/*
 * Build a cal_state_t with identical floor/ceiling on all channels.
 * Sets unconfigured[] to false on all channels (the test must override
 * individual channels as needed).
 */
static cal_state_t make_cal(float floor_val, float ceiling_val)
{
    cal_state_t cal;
    for (int i = 0; i < CAL_NUM_CHANNELS; i++) {
        cal.floor[i]        = floor_val;
        cal.ceiling[i]      = ceiling_val;
        cal.unconfigured[i] = false;
    }
    return cal;
}

/*
 * Build a scan_result_t with the same raw value on all channels.
 * carrier_mag is set separately for passthrough tests.
 */
static scan_result_t make_scan(float stdev, float gsr0, float gsr1,
                                float gsr2, float carrier)
{
    scan_result_t s;
    s.self_stdev       = stdev;
    s.gsr_mag[0]       = gsr0;
    s.gsr_mag[1]       = gsr1;
    s.gsr_mag[2]       = gsr2;
    s.self_carrier_mag = carrier;
    s.node_id          = 0;
    s.gsr_node[0]      = 1;
    s.gsr_node[1]      = 2;
    s.gsr_node[2]      = 3;
    return s;
}

/* =========================================================================
 * calibration_apply tests
 * ========================================================================= */

/*
 * Normal range: raw at the midpoint of floor..ceiling.
 * floor=100, ceiling=300, raw=200 → expected output 0.5 on every channel.
 */
static void test_apply_normal_range(void)
{
    cal_state_t   cal = make_cal(100.0f, 300.0f);
    scan_result_t raw = make_scan(200.0f, 200.0f, 200.0f, 200.0f, 0.0f);
    float out[CAL_NUM_CHANNELS];
    float carrier_mag;

    calibration_apply(&cal, &raw, out, &carrier_mag);

    for (int i = 0; i < CAL_NUM_CHANNELS; i++) {
        TEST_ASSERT(out[i] >= 0.0f);
        TEST_ASSERT(out[i] <= 1.0f);
        TEST_ASSERT_FLOAT_NEAR(out[i], 0.5f, 0.001f);
    }
}

/*
 * At floor: raw == floor → output must be exactly 0.0.
 */
static void test_apply_at_floor(void)
{
    cal_state_t   cal = make_cal(100.0f, 300.0f);
    scan_result_t raw = make_scan(100.0f, 100.0f, 100.0f, 100.0f, 0.0f);
    float out[CAL_NUM_CHANNELS];
    float carrier_mag;

    calibration_apply(&cal, &raw, out, &carrier_mag);

    for (int i = 0; i < CAL_NUM_CHANNELS; i++) {
        TEST_ASSERT_FLOAT_NEAR(out[i], 0.0f, 0.0001f);
    }
}

/*
 * At ceiling: raw == ceiling → output must be exactly 1.0.
 */
static void test_apply_at_ceiling(void)
{
    cal_state_t   cal = make_cal(100.0f, 300.0f);
    scan_result_t raw = make_scan(300.0f, 300.0f, 300.0f, 300.0f, 0.0f);
    float out[CAL_NUM_CHANNELS];
    float carrier_mag;

    calibration_apply(&cal, &raw, out, &carrier_mag);

    for (int i = 0; i < CAL_NUM_CHANNELS; i++) {
        TEST_ASSERT_FLOAT_NEAR(out[i], 1.0f, 0.0001f);
    }
}

/*
 * Below floor: raw < floor → clamped to 0.0.
 */
static void test_apply_below_floor_clamped(void)
{
    cal_state_t   cal = make_cal(100.0f, 300.0f);
    scan_result_t raw = make_scan(50.0f, 50.0f, 50.0f, 50.0f, 0.0f);
    float out[CAL_NUM_CHANNELS];
    float carrier_mag;

    calibration_apply(&cal, &raw, out, &carrier_mag);

    for (int i = 0; i < CAL_NUM_CHANNELS; i++) {
        TEST_ASSERT_FLOAT_NEAR(out[i], 0.0f, 0.0001f);
    }
}

/*
 * Above ceiling: raw > ceiling → clamped to 1.0.
 */
static void test_apply_above_ceiling_clamped(void)
{
    cal_state_t   cal = make_cal(100.0f, 300.0f);
    scan_result_t raw = make_scan(500.0f, 500.0f, 500.0f, 500.0f, 0.0f);
    float out[CAL_NUM_CHANNELS];
    float carrier_mag;

    calibration_apply(&cal, &raw, out, &carrier_mag);

    for (int i = 0; i < CAL_NUM_CHANNELS; i++) {
        TEST_ASSERT_FLOAT_NEAR(out[i], 1.0f, 0.0001f);
    }
}

/*
 * Unconfigured channel: output must be 0.0 regardless of raw value.
 * Mark only channel 2 as unconfigured; the rest are normal.
 * Use a mid-range raw value (200.0 with floor=100, ceil=300 → 0.5) so
 * configured channels produce ~0.5, making a bug that always returns 0.0
 * distinguishable from correct unconfigured-channel suppression.
 */
static void test_apply_unconfigured_channel(void)
{
    cal_state_t cal = make_cal(100.0f, 300.0f);
    cal.unconfigured[2] = true;

    /* Raw at midpoint — configured channels produce 0.5, not 1.0. */
    scan_result_t raw = make_scan(200.0f, 200.0f, 200.0f, 200.0f, 0.0f);
    float out[CAL_NUM_CHANNELS];
    float carrier_mag;

    calibration_apply(&cal, &raw, out, &carrier_mag);

    /* Channels 0, 1, 3 should be at midpoint (0.5). */
    TEST_ASSERT_FLOAT_NEAR(out[0], 0.5f, 0.001f);
    TEST_ASSERT_FLOAT_NEAR(out[1], 0.5f, 0.001f);
    /* Channel 2 is unconfigured → 0.0. */
    TEST_ASSERT_FLOAT_NEAR(out[2], 0.0f, 0.0001f);
    TEST_ASSERT_FLOAT_NEAR(out[3], 0.5f, 0.001f);
}

/*
 * carrier_mag passthrough: calibration_apply must copy self_carrier_mag
 * into *carrier_mag unchanged.
 */
static void test_apply_carrier_mag_passthrough(void)
{
    cal_state_t   cal = make_cal(0.0f, 1000.0f);
    float carrier_in  = 42.5f;
    scan_result_t raw = make_scan(500.0f, 500.0f, 500.0f, 500.0f, carrier_in);
    float out[CAL_NUM_CHANNELS];
    float carrier_mag = 0.0f;

    calibration_apply(&cal, &raw, out, &carrier_mag);

    TEST_ASSERT_FLOAT_NEAR(carrier_mag, carrier_in, 0.0001f);
}

/* =========================================================================
 * calibration_init tests
 *
 * Channel index mapping (must match calibration_init):
 *   0 = self_stdev,  1 = gsr0,  2 = gsr1,  3 = gsr2
 * ========================================================================= */

/*
 * Helper: build a node_config_t using the new ceil_* fields.
 * All four channels get the same floor/ceiling values.
 */
static node_config_t make_cfg(uint16_t floor_val, uint16_t ceil_val)
{
    node_config_t cfg;
    cfg.node_id   = 0;
    cfg.base_k    = BASE_K_DEFAULT;
    cfg.step_k    = STEP_K_DEFAULT;
    cfg.window_n  = WINDOW_N_DEFAULT;
    cfg.floor_stdev = floor_val;
    cfg.floor_gsr0  = floor_val;
    cfg.floor_gsr1  = floor_val;
    cfg.floor_gsr2  = floor_val;
    cfg.ceil_stdev  = ceil_val;
    cfg.ceil_gsr0   = ceil_val;
    cfg.ceil_gsr1   = ceil_val;
    cfg.ceil_gsr2   = ceil_val;
    return cfg;
}

/*
 * Normal config (floor < ceiling, not sentinel): all channels configured.
 */
static void test_init_normal_config(void)
{
    node_config_t cfg = make_cfg(100, 300);
    cal_state_t   cal;

    calibration_init(&cal, &cfg);

    for (int i = 0; i < CAL_NUM_CHANNELS; i++) {
        TEST_ASSERT(cal.unconfigured[i] == false);
        TEST_ASSERT_FLOAT_NEAR(cal.floor[i],   100.0f, 0.001f);
        TEST_ASSERT_FLOAT_NEAR(cal.ceiling[i], 300.0f, 0.001f);
    }
}

/*
 * Ceiling == sentinel (CAL_CEIL_DEFAULT = 65535): all channels unconfigured.
 */
static void test_init_ceiling_sentinel(void)
{
    node_config_t cfg = make_cfg(0, CAL_CEIL_DEFAULT);
    cal_state_t   cal;

    calibration_init(&cal, &cfg);

    for (int i = 0; i < CAL_NUM_CHANNELS; i++) {
        TEST_ASSERT(cal.unconfigured[i] == true);
    }
}

/*
 * Ceiling == floor: degenerate range → unconfigured.
 */
static void test_init_ceiling_equals_floor(void)
{
    node_config_t cfg = make_cfg(200, 200);
    cal_state_t   cal;

    calibration_init(&cal, &cfg);

    for (int i = 0; i < CAL_NUM_CHANNELS; i++) {
        TEST_ASSERT(cal.unconfigured[i] == true);
    }
}

/*
 * Ceiling < floor: inverted range → unconfigured.
 */
static void test_init_ceiling_less_than_floor(void)
{
    node_config_t cfg = make_cfg(300, 100);
    cal_state_t   cal;

    calibration_init(&cal, &cfg);

    for (int i = 0; i < CAL_NUM_CHANNELS; i++) {
        TEST_ASSERT(cal.unconfigured[i] == true);
    }
}

/*
 * Default config (floor=CAL_FLOOR_DEFAULT=0, ceiling=CAL_CEIL_DEFAULT=65535):
 * all channels unconfigured (ceiling is the sentinel).
 */
static void test_init_default_config(void)
{
    node_config_t cfg = make_cfg(CAL_FLOOR_DEFAULT, CAL_CEIL_DEFAULT);
    cal_state_t   cal;

    calibration_init(&cal, &cfg);

    for (int i = 0; i < CAL_NUM_CHANNELS; i++) {
        TEST_ASSERT(cal.unconfigured[i] == true);
    }
}

/*
 * Mixed channels: some configured, some not.
 *   ch0 (stdev): floor=100, ceil=300  → configured
 *   ch1 (gsr0):  floor=0,   ceil=65535 → sentinel → unconfigured
 *   ch2 (gsr1):  floor=50,  ceil=250  → configured
 *   ch3 (gsr2):  floor=200, ceil=200  → ceil==floor → unconfigured
 *
 * Constructed manually because make_cfg sets all channels the same.
 */
static void test_init_mixed_channels(void)
{
    node_config_t cfg;
    cfg.node_id    = 0;
    cfg.base_k     = BASE_K_DEFAULT;
    cfg.step_k     = STEP_K_DEFAULT;
    cfg.window_n   = WINDOW_N_DEFAULT;

    cfg.floor_stdev = 100;  cfg.ceil_stdev = 300;
    cfg.floor_gsr0  = 0;    cfg.ceil_gsr0  = CAL_CEIL_DEFAULT; /* sentinel */
    cfg.floor_gsr1  = 50;   cfg.ceil_gsr1  = 250;
    cfg.floor_gsr2  = 200;  cfg.ceil_gsr2  = 200;              /* ceil==floor */

    cal_state_t cal;
    calibration_init(&cal, &cfg);

    /* Configured channels */
    TEST_ASSERT(cal.unconfigured[0] == false);
    TEST_ASSERT_FLOAT_NEAR(cal.floor[0],   100.0f, 0.001f);
    TEST_ASSERT_FLOAT_NEAR(cal.ceiling[0], 300.0f, 0.001f);

    TEST_ASSERT(cal.unconfigured[2] == false);
    TEST_ASSERT_FLOAT_NEAR(cal.floor[2],    50.0f, 0.001f);
    TEST_ASSERT_FLOAT_NEAR(cal.ceiling[2], 250.0f, 0.001f);

    /* Unconfigured channels */
    TEST_ASSERT(cal.unconfigured[1] == true);
    TEST_ASSERT(cal.unconfigured[3] == true);
}

/* =========================================================================
 * main
 * ========================================================================= */

int main(void)
{
    /* calibration_apply */
    RUN_TEST(test_apply_normal_range);
    RUN_TEST(test_apply_at_floor);
    RUN_TEST(test_apply_at_ceiling);
    RUN_TEST(test_apply_below_floor_clamped);
    RUN_TEST(test_apply_above_ceiling_clamped);
    RUN_TEST(test_apply_unconfigured_channel);
    RUN_TEST(test_apply_carrier_mag_passthrough);

    /* calibration_init */
    RUN_TEST(test_init_normal_config);
    RUN_TEST(test_init_ceiling_sentinel);
    RUN_TEST(test_init_ceiling_equals_floor);
    RUN_TEST(test_init_ceiling_less_than_floor);
    RUN_TEST(test_init_default_config);
    RUN_TEST(test_init_mixed_channels);

    return TEST_REPORT();
}
