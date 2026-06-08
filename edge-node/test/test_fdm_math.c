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
 * Hann window tests
 * ========================================================================= */

/*
 * Endpoints: for n=1024, out[0] and out[n-1] should be ≈ 0.0 (within 0.001).
 * The standard Hann window formula w[i] = 0.5*(1 - cos(2*PI*i/(n-1))) gives
 * w[0]=0 and w[n-1]=0.
 */
static void test_hann_window_endpoints(void)
{
    static float win[1024];
    fdm_hann_window(win, 1024);
    TEST_ASSERT_FLOAT_NEAR(win[0],    0.0f, 0.001f);
    TEST_ASSERT_FLOAT_NEAR(win[1023], 0.0f, 0.001f);
}

/*
 * Midpoint: for n=1024, out[n/2] = out[512] should be ≈ 1.0 (within 0.001).
 * At i=512 with n=1024: w[512] = 0.5*(1 - cos(2*PI*512/1023)) ≈ 1.0.
 */
static void test_hann_window_midpoint(void)
{
    static float win[1024];
    fdm_hann_window(win, 1024);
    TEST_ASSERT_FLOAT_NEAR(win[512], 1.0f, 0.001f);
}

/*
 * Symmetry: for n=1024, out[i] should equal out[n-1-i] for several i values
 * (within 0.0001).
 */
static void test_hann_window_symmetry(void)
{
    static float win[1024];
    fdm_hann_window(win, 1024);
    const int indices[] = {1, 10, 100, 256, 400};
    for (int t = 0; t < 5; t++) {
        int i = indices[t];
        TEST_ASSERT_FLOAT_NEAR(win[i], win[1023 - i], 0.0001f);
    }
}

/* =========================================================================
 * FFT tests
 * ========================================================================= */

/*
 * DC input: fill 2048-point FFT with constant (all re=1.0, im=0.0).
 * After FFT, bin 0 magnitude should be 2048.0 (within 1%), all other bins
 * should have magnitude < 1.0.
 */
static void test_fft_dc_input(void)
{
    static float fft_buf[4096];  /* 2*N interleaved complex */
    const int N = 2048;
    for (int i = 0; i < N; i++) {
        fft_buf[2*i]   = 1.0f;  /* real */
        fft_buf[2*i+1] = 0.0f;  /* imag */
    }

    fdm_fft_radix2(fft_buf, N);

    /* Bin 0 magnitude = sqrt(re^2 + im^2) */
    float mag0 = sqrtf(fft_buf[0]*fft_buf[0] + fft_buf[1]*fft_buf[1]);
    TEST_ASSERT_FLOAT_NEAR(mag0, (float)N, (float)N * 0.01f);

    /* All other bins should be near zero */
    for (int k = 1; k < N; k++) {
        float re = fft_buf[2*k];
        float im = fft_buf[2*k+1];
        float mag = sqrtf(re*re + im*im);
        TEST_ASSERT(mag < 1.0f);
    }
}

/*
 * Pure cosine: real[n] = cos(2*PI*100*n/2048), imag=0.
 * After FFT, bin 100 should have the largest magnitude (≈ N/2 = 1024.0,
 * within 5%).  Bin 500 (far from the signal) should be < 1.0.
 */
static void test_fft_pure_sine(void)
{
    static float fft_buf[4096];
    const int N   = 2048;
    const int k   = 100;
    const float EXPECT = (float)N / 2.0f;  /* 1024.0 */

    for (int n = 0; n < N; n++) {
        fft_buf[2*n]   = cosf(2.0f * (float)M_PI * k * n / N);
        fft_buf[2*n+1] = 0.0f;
    }

    fdm_fft_radix2(fft_buf, N);

    float re100 = fft_buf[2*100];
    float im100 = fft_buf[2*100+1];
    float mag100 = sqrtf(re100*re100 + im100*im100);
    TEST_ASSERT_FLOAT_NEAR(mag100, EXPECT, EXPECT * 0.05f);

    float re500 = fft_buf[2*500];
    float im500 = fft_buf[2*500+1];
    float mag500 = sqrtf(re500*re500 + im500*im500);
    TEST_ASSERT(mag500 < 1.0f);
}

/*
 * Linearity: two amplitudes (A=1.0 and A=2.0) at the same bin should produce
 * proportional FFT magnitudes.  ratio = mag_A2 / mag_A1 should be ≈ 2.0
 * (within 1%).
 */
static void test_fft_linearity(void)
{
    static float buf1[4096];
    static float buf2[4096];
    const int N = 2048;
    const int k = 100;

    for (int n = 0; n < N; n++) {
        buf1[2*n]   = 1.0f * cosf(2.0f * (float)M_PI * k * n / N);
        buf1[2*n+1] = 0.0f;
        buf2[2*n]   = 2.0f * cosf(2.0f * (float)M_PI * k * n / N);
        buf2[2*n+1] = 0.0f;
    }

    fdm_fft_radix2(buf1, N);
    fdm_fft_radix2(buf2, N);

    float re1 = buf1[2*k], im1 = buf1[2*k+1];
    float re2 = buf2[2*k], im2 = buf2[2*k+1];
    float mag1 = sqrtf(re1*re1 + im1*im1);
    float mag2 = sqrtf(re2*re2 + im2*im2);

    /* mag1 must be nonzero before dividing */
    TEST_ASSERT(mag1 > 1.0f);
    float ratio = mag2 / mag1;
    TEST_ASSERT_FLOAT_NEAR(ratio, 2.0f, 2.0f * 0.01f);
}

/* =========================================================================
 * Log-magnitude tests
 * ========================================================================= */

/*
 * Full scale: bin 0 has re=10000, im=0, all others zero.
 * The output u8 for bin 0 should be 255.
 */
static void test_log_magnitudes_full_scale(void)
{
    static float fft_data[4096];
    static uint8_t out[1024];
    const int N = 2048;

    for (int i = 0; i < 2*N; i++) fft_data[i] = 0.0f;
    fft_data[0] = 10000.0f;  /* re of bin 0 */
    fft_data[1] = 0.0f;      /* im of bin 0 */

    fdm_fft_log_magnitudes(fft_data, N, out);

    TEST_ASSERT_INT_EQ((int)out[0], 255);
}

/*
 * Noise floor: all bins near zero → all output u8 values should be 0.
 */
static void test_log_magnitudes_noise_floor(void)
{
    static float fft_data[4096];
    static uint8_t out[1024];
    const int N = 2048;

    for (int i = 0; i < 2*N; i++) fft_data[i] = 0.0f;

    fdm_fft_log_magnitudes(fft_data, N, out);

    for (int k = 0; k < N/2; k++) {
        TEST_ASSERT_INT_EQ((int)out[k], 0);
    }
}

/*
 * Dynamic range: a bin 48 dB below full scale should map to roughly 128
 * (half of 255), within ±10, since 48 dB is half of the 96 dB range.
 *
 * Full-scale reference: bin 0 re=10000.  48 dB down means magnitude is
 * 10000 / 10^(48/20) ≈ 10000 / 251.19 ≈ 39.81.  Place that in bin 1.
 */
static void test_log_magnitudes_dynamic_range(void)
{
    static float fft_data[4096];
    static uint8_t out[1024];
    const int N = 2048;

    for (int i = 0; i < 2*N; i++) fft_data[i] = 0.0f;

    /* Full-scale bin */
    fft_data[0] = 10000.0f;
    fft_data[1] = 0.0f;

    /* 48 dB below full scale: magnitude = 10000 / 10^(48/20) */
    float mag_48db = 10000.0f / powf(10.0f, 48.0f / 20.0f);
    fft_data[2] = mag_48db;  /* re of bin 1 */
    fft_data[3] = 0.0f;      /* im of bin 1 */

    fdm_fft_log_magnitudes(fft_data, N, out);

    TEST_ASSERT_INT_EQ((int)out[0], 255);
    /* bin 1 should be near 128 (48/96 * 255 ≈ 127.5), tolerance ±10 */
    TEST_ASSERT(out[1] >= 118 && out[1] <= 138);
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

    /* Hann window */
    RUN_TEST(test_hann_window_endpoints);
    RUN_TEST(test_hann_window_midpoint);
    RUN_TEST(test_hann_window_symmetry);

    /* FFT */
    RUN_TEST(test_fft_dc_input);
    RUN_TEST(test_fft_pure_sine);
    RUN_TEST(test_fft_linearity);

    /* Log magnitudes */
    RUN_TEST(test_log_magnitudes_full_scale);
    RUN_TEST(test_log_magnitudes_noise_floor);
    RUN_TEST(test_log_magnitudes_dynamic_range);

    return TEST_REPORT();
}
