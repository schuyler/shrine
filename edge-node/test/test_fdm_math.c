/**
 * test_fdm_math.c — Host-side unit tests for the FDM math module.
 *
 * Compiled and run on the host (not on the ESP32).  No IDF dependencies.
 *
 * Test harness: test_utils.h (minimal, provided separately).
 *   TEST_ASSERT(cond)
 *   TEST_ASSERT_FLOAT_NEAR(a, b, tol)
 *   TEST_ASSERT_INT_EQ(a, b)
 *   RUN_TEST(func)
 *   TEST_REPORT()  → returns 0 on all-pass
 */

#include "test_utils.h"
#include "../src/fdm_math.h"

#include <math.h>
#include <stdint.h>

/* =========================================================================
 * Helpers
 * ========================================================================= */

#ifndef M_PI
#define M_PI 3.14159265358979323846
#endif

/* =========================================================================
 * NCO I/Q demodulation tests
 * ========================================================================= */

/*
 * Pure sine at target bin: 1800 samples of sin at k=180, N=1800, amplitude=500
 * centered at DC=2048.  DFT of A*sin(2*PI*k*n/N) at the matching bin gives
 * magnitude A/2 after the sqrt(I^2+Q^2)/N normalization.
 *
 * Expected magnitude ≈ 250.0, tolerance 5% (12.5).
 */
static void test_demod_pure_sine_at_target_bin(void)
{
    const int     N   = 1800;
    const float   A   = 500.0f;
    const int     k   = 180;
    const float   EXPECT = A / 2.0f;   /* 250.0 */

    uint16_t samples[1800];
    for (int n = 0; n < N; n++) {
        samples[n] = (uint16_t)(2048.0f + A * sinf(2.0f * (float)M_PI * k * n / N));
    }

    float cos_step = cosf(2.0f * (float)M_PI * k / N);
    float sin_step = -sinf(2.0f * (float)M_PI * k / N);
    float mag = fdm_demod_magnitude(samples, N, cos_step, sin_step);

    TEST_ASSERT_FLOAT_NEAR(mag, EXPECT, EXPECT * 0.05f);
}

/*
 * Sine at wrong bin: signal at k=200, demodulate at k=180.
 * Bins are orthogonal (spacing 20, N=1800), so the result should be ~0.
 * Accept magnitude < 5.0.
 */
static void test_demod_pure_sine_at_wrong_bin(void)
{
    const int   N        = 1800;
    const float A        = 500.0f;
    const int   k_signal = 200;
    const int   k_demod  = 180;

    uint16_t samples[1800];
    for (int n = 0; n < N; n++) {
        samples[n] = (uint16_t)(2048.0f + A * sinf(2.0f * (float)M_PI * k_signal * n / N));
    }

    float cos_step = cosf(2.0f * (float)M_PI * k_demod / N);
    float sin_step = -sinf(2.0f * (float)M_PI * k_demod / N);
    float mag = fdm_demod_magnitude(samples, N, cos_step, sin_step);

    TEST_ASSERT(mag < 5.0f);
}

/*
 * DC rejection: all samples = 2048.
 * After DC removal every sample is 0, so magnitude must be < 1.0.
 */
static void test_demod_dc_rejection(void)
{
    const int N = 1800;
    const int k = 180;

    uint16_t samples[1800];
    for (int i = 0; i < N; i++) {
        samples[i] = 2048;
    }

    float cos_step = cosf(2.0f * (float)M_PI * k / N);
    float sin_step = -sinf(2.0f * (float)M_PI * k / N);
    float mag = fdm_demod_magnitude(samples, N, cos_step, sin_step);

    TEST_ASSERT(mag < 1.0f);
}

/*
 * Known magnitude with amplitude=1000: verify linear scaling.
 * Expected magnitude ≈ 500.0, tolerance 5% (25.0).
 */
static void test_demod_known_magnitude(void)
{
    const int   N = 1800;
    const float A = 1000.0f;
    const int   k = 180;
    const float EXPECT = A / 2.0f;   /* 500.0 */

    uint16_t samples[1800];
    for (int n = 0; n < N; n++) {
        samples[n] = (uint16_t)(2048.0f + A * sinf(2.0f * (float)M_PI * k * n / N));
    }

    float cos_step = cosf(2.0f * (float)M_PI * k / N);
    float sin_step = -sinf(2.0f * (float)M_PI * k / N);
    float mag = fdm_demod_magnitude(samples, N, cos_step, sin_step);

    TEST_ASSERT_FLOAT_NEAR(mag, EXPECT, EXPECT * 0.05f);
}

/*
 * Long window to stress NCO renormalization: N=7200 (112 renorm cycles at
 * every-64).  Same frequency ratio as the N=1800 tests (k/N = 1/10).
 * Without renormalization, phasor drift accumulates over 7200 rotations.
 * Tight tolerance (1%) to catch drift that the 5% tests would miss.
 *
 * k=720 at N=7200 gives the same physical frequency as k=180 at N=1800.
 */
static void test_demod_long_window_renorm(void)
{
    const int   N = 7200;
    const float A = 500.0f;
    const int   k = 720;
    const float EXPECT = A / 2.0f;   /* 250.0 */

    static uint16_t samples[7200];
    for (int n = 0; n < N; n++) {
        samples[n] = (uint16_t)(2048.0f + A * sinf(2.0f * (float)M_PI * k * n / N));
    }

    float cos_step = cosf(2.0f * (float)M_PI * k / N);
    float sin_step = -sinf(2.0f * (float)M_PI * k / N);
    float mag = fdm_demod_magnitude(samples, N, cos_step, sin_step);

    TEST_ASSERT_FLOAT_NEAR(mag, EXPECT, EXPECT * 0.01f);
}

/*
 * Renorm boundary: N=65 (just past the first renormalization point at
 * sample 64).  Catches off-by-one errors in the renorm interval check.
 * k=5 gives an integer-bin sine at N=65 (5 complete cycles in 65 samples).
 */
static void test_demod_renorm_boundary(void)
{
    const int   N = 65;
    const float A = 500.0f;
    const int   k = 5;
    const float EXPECT = A / 2.0f;   /* 250.0 */

    uint16_t samples[65];
    for (int n = 0; n < N; n++) {
        samples[n] = (uint16_t)(2048.0f + A * sinf(2.0f * (float)M_PI * k * n / N));
    }

    float cos_step = cosf(2.0f * (float)M_PI * k / N);
    float sin_step = -sinf(2.0f * (float)M_PI * k / N);
    float mag = fdm_demod_magnitude(samples, N, cos_step, sin_step);

    TEST_ASSERT_FLOAT_NEAR(mag, EXPECT, EXPECT * 0.02f);
}

/* =========================================================================
 * Stdev tests
 * ========================================================================= */

/*
 * Constant signal: all samples = 2048.
 * Stdev must be within 0.01 of 0.0.
 */
static void test_stdev_constant_signal(void)
{
    const int N = 1800;

    uint16_t samples[1800];
    for (int i = 0; i < N; i++) {
        samples[i] = 2048;
    }

    float sd = fdm_stdev(samples, N);
    TEST_ASSERT_FLOAT_NEAR(sd, 0.0f, 0.01f);
}

/*
 * Known distribution: alternating 2000 and 2100 (900 of each in 1800 samples).
 * Mean = 2050, variance = 2500, stdev = 50.0.
 * Assert within 1.0.
 */
static void test_stdev_known_distribution(void)
{
    const int N = 1800;

    uint16_t samples[1800];
    for (int i = 0; i < N; i++) {
        samples[i] = (i % 2 == 0) ? 2000 : 2100;
    }

    float sd = fdm_stdev(samples, N);
    TEST_ASSERT_FLOAT_NEAR(sd, 50.0f, 1.0f);
}

/*
 * Nonzero for varying signal: samples alternating between 1000 and 3000.
 * Stdev must be > 0.
 */
static void test_stdev_nonzero_for_varying_signal(void)
{
    const int N = 1800;

    uint16_t samples[1800];
    for (int i = 0; i < N; i++) {
        samples[i] = (i % 2 == 0) ? 1000 : 3000;
    }

    float sd = fdm_stdev(samples, N);
    TEST_ASSERT(sd > 0.0f);
}

/* =========================================================================
 * GSR ordering tests
 * ========================================================================= */

/*
 * node_id=0, num_nodes=4: expect gsr_node = [1, 2, 3]
 */
static void test_gsr_ordering_node0(void)
{
    uint8_t gsr_node[3] = {0xFF, 0xFF, 0xFF};
    fdm_gsr_ordering(0, 4, gsr_node);
    TEST_ASSERT_INT_EQ((int)gsr_node[0], 1);
    TEST_ASSERT_INT_EQ((int)gsr_node[1], 2);
    TEST_ASSERT_INT_EQ((int)gsr_node[2], 3);
}

/*
 * node_id=1, num_nodes=4: expect gsr_node = [2, 3, 0]
 */
static void test_gsr_ordering_node1(void)
{
    uint8_t gsr_node[3] = {0xFF, 0xFF, 0xFF};
    fdm_gsr_ordering(1, 4, gsr_node);
    TEST_ASSERT_INT_EQ((int)gsr_node[0], 2);
    TEST_ASSERT_INT_EQ((int)gsr_node[1], 3);
    TEST_ASSERT_INT_EQ((int)gsr_node[2], 0);
}

/*
 * node_id=2, num_nodes=4: expect gsr_node = [3, 0, 1]
 */
static void test_gsr_ordering_node2(void)
{
    uint8_t gsr_node[3] = {0xFF, 0xFF, 0xFF};
    fdm_gsr_ordering(2, 4, gsr_node);
    TEST_ASSERT_INT_EQ((int)gsr_node[0], 3);
    TEST_ASSERT_INT_EQ((int)gsr_node[1], 0);
    TEST_ASSERT_INT_EQ((int)gsr_node[2], 1);
}

/*
 * node_id=3, num_nodes=4: expect gsr_node = [0, 1, 2]
 */
static void test_gsr_ordering_node3(void)
{
    uint8_t gsr_node[3] = {0xFF, 0xFF, 0xFF};
    fdm_gsr_ordering(3, 4, gsr_node);
    TEST_ASSERT_INT_EQ((int)gsr_node[0], 0);
    TEST_ASSERT_INT_EQ((int)gsr_node[1], 1);
    TEST_ASSERT_INT_EQ((int)gsr_node[2], 2);
}

/* =========================================================================
 * main
 * ========================================================================= */

int main(void)
{
    /* NCO I/Q demodulation */
    RUN_TEST(test_demod_pure_sine_at_target_bin);
    RUN_TEST(test_demod_pure_sine_at_wrong_bin);
    RUN_TEST(test_demod_dc_rejection);
    RUN_TEST(test_demod_known_magnitude);

    RUN_TEST(test_demod_long_window_renorm);
    RUN_TEST(test_demod_renorm_boundary);

    /* Stdev */
    RUN_TEST(test_stdev_constant_signal);
    RUN_TEST(test_stdev_known_distribution);
    RUN_TEST(test_stdev_nonzero_for_varying_signal);

    /* GSR ordering */
    RUN_TEST(test_gsr_ordering_node0);
    RUN_TEST(test_gsr_ordering_node1);
    RUN_TEST(test_gsr_ordering_node2);
    RUN_TEST(test_gsr_ordering_node3);

    return TEST_REPORT();
}
