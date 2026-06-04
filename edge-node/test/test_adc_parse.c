/**
 * test_adc_parse.c — Host-side unit tests for adc_parse_frame() and
 * window_accumulate().
 *
 * Compiled and run on the host (not on the ESP32).  No IDF dependencies.
 *
 * Test harness: test_utils.h (minimal, provided separately).
 *   TEST_ASSERT(cond)
 *   TEST_ASSERT_INT_EQ(a, b)
 *   RUN_TEST(func)
 *   TEST_REPORT()  → returns 0 on all-pass
 */

#include "test_utils.h"
#include "../src/adc_parse.h"

#include <stdint.h>
#include <string.h>

/*
 * SOC_ADC_DIGI_RESULT_BYTES is normally defined by ESP-IDF.  Define it here
 * for host compilation so the test documents the assumed DMA format.
 */
#define SOC_ADC_DIGI_RESULT_BYTES 2

/* =========================================================================
 * Helper
 * ========================================================================= */

/*
 * Build a TYPE1 DMA frame in buf[].
 * Each sample occupies SOC_ADC_DIGI_RESULT_BYTES (2) bytes, little-endian:
 *   bits [11:0]  = 12-bit ADC data (values & 0x0FFF)
 *   bits [15:12] = channel (channel & 0xF) << 12
 */
static void make_type1_frame(uint8_t *buf, const uint16_t *values,
                              int n_samples, uint8_t channel)
{
    for (int i = 0; i < n_samples; i++) {
        uint16_t word = (uint16_t)((values[i] & 0x0FFFu) |
                                   (((uint16_t)(channel & 0xFu)) << 12));
        buf[i * SOC_ADC_DIGI_RESULT_BYTES + 0] = (uint8_t)(word & 0xFFu);
        buf[i * SOC_ADC_DIGI_RESULT_BYTES + 1] = (uint8_t)((word >> 8) & 0xFFu);
    }
}

/* =========================================================================
 * adc_parse_frame tests
 * ========================================================================= */

/*
 * 4 known 12-bit values with channel=0.
 * Verify that the exact data values are extracted.
 */
static void test_parse_known_values(void)
{
    const uint16_t vals[4] = {0, 2048, 4095, 1234};
    uint8_t raw[4 * SOC_ADC_DIGI_RESULT_BYTES];
    uint16_t out[4];

    make_type1_frame(raw, vals, 4, 0);
    int n = adc_parse_frame(raw, (int)sizeof(raw), out, 4);

    TEST_ASSERT_INT_EQ(n, 4);
    TEST_ASSERT_INT_EQ((int)out[0], 0);
    TEST_ASSERT_INT_EQ((int)out[1], 2048);
    TEST_ASSERT_INT_EQ((int)out[2], 4095);
    TEST_ASSERT_INT_EQ((int)out[3], 1234);
}

/*
 * Same 4 values encoded with channel=5.
 * The channel bits must be stripped; the 12-bit data must be identical.
 */
static void test_parse_with_channel_bits(void)
{
    const uint16_t vals[4] = {0, 2048, 4095, 1234};
    uint8_t raw[4 * SOC_ADC_DIGI_RESULT_BYTES];
    uint16_t out[4];

    make_type1_frame(raw, vals, 4, 5);
    int n = adc_parse_frame(raw, (int)sizeof(raw), out, 4);

    TEST_ASSERT_INT_EQ(n, 4);
    TEST_ASSERT_INT_EQ((int)out[0], 0);
    TEST_ASSERT_INT_EQ((int)out[1], 2048);
    TEST_ASSERT_INT_EQ((int)out[2], 4095);
    TEST_ASSERT_INT_EQ((int)out[3], 1234);
}

/*
 * raw_len = 3: one complete 2-byte entry plus 1 leftover byte.
 * Must return 1 (the complete sample only).
 */
static void test_parse_partial_frame(void)
{
    const uint16_t vals[2] = {100, 200};
    uint8_t raw[2 * SOC_ADC_DIGI_RESULT_BYTES];
    uint16_t out[2];

    make_type1_frame(raw, vals, 2, 0);
    /* Pass only 3 bytes: 1 complete sample + 1 stray byte */
    int n = adc_parse_frame(raw, 3, out, 2);

    TEST_ASSERT_INT_EQ(n, 1);
    TEST_ASSERT_INT_EQ((int)out[0], 100);
}

/*
 * raw_len = 0: empty frame, must return 0 immediately.
 */
static void test_parse_zero_length(void)
{
    uint16_t out[4];
    int n = adc_parse_frame(NULL, 0, out, 4);
    TEST_ASSERT_INT_EQ(n, 0);
}

/*
 * 8 samples in the frame but max_out = 3.
 * Must stop after writing 3 samples and return 3.
 */
static void test_parse_max_out_limit(void)
{
    const uint16_t vals[8] = {10, 20, 30, 40, 50, 60, 70, 80};
    uint8_t raw[8 * SOC_ADC_DIGI_RESULT_BYTES];
    uint16_t out[8];

    make_type1_frame(raw, vals, 8, 0);
    int n = adc_parse_frame(raw, (int)sizeof(raw), out, 3);

    TEST_ASSERT_INT_EQ(n, 3);
    TEST_ASSERT_INT_EQ((int)out[0], 10);
    TEST_ASSERT_INT_EQ((int)out[1], 20);
    TEST_ASSERT_INT_EQ((int)out[2], 30);
}

/* =========================================================================
 * window_accumulate tests
 * ========================================================================= */

/*
 * 5 samples into window_size=10: window is not yet full.
 * Returns 0 and *pos == 5.
 */
static void test_accumulate_partial_fill(void)
{
    uint16_t window[10];
    uint16_t snapshot[10];
    int pos = 0;

    uint16_t samples[5] = {1, 2, 3, 4, 5};
    int fills = window_accumulate(window, 10, &pos, samples, 5, snapshot);

    TEST_ASSERT_INT_EQ(fills, 0);
    TEST_ASSERT_INT_EQ(pos, 5);
}

/*
 * 10 samples into window_size=10: exactly one complete fill.
 * Returns 1, *pos == 0, and snapshot contains the 10 samples.
 */
static void test_accumulate_exact_fill(void)
{
    uint16_t window[10];
    uint16_t snapshot[10];
    int pos = 0;

    uint16_t samples[10];
    for (int i = 0; i < 10; i++) {
        samples[i] = (uint16_t)(100 + i);
    }

    int fills = window_accumulate(window, 10, &pos, samples, 10, snapshot);

    TEST_ASSERT_INT_EQ(fills, 1);
    TEST_ASSERT_INT_EQ(pos, 0);
    for (int i = 0; i < 10; i++) {
        TEST_ASSERT_INT_EQ((int)snapshot[i], 100 + i);
    }
}

/*
 * 12 samples into window_size=10: window fills once with samples[0..9],
 * then 2 remaining samples start the next window.
 * Returns 1, *pos == 2, window[0]==samples[10], window[1]==samples[11].
 */
static void test_accumulate_overfill(void)
{
    uint16_t window[10];
    uint16_t snapshot[10];
    int pos = 0;

    uint16_t samples[12];
    for (int i = 0; i < 12; i++) {
        samples[i] = (uint16_t)(200 + i);
    }

    int fills = window_accumulate(window, 10, &pos, samples, 12, snapshot);

    TEST_ASSERT_INT_EQ(fills, 1);
    TEST_ASSERT_INT_EQ(pos, 2);
    /* First 2 samples of the next window are in place */
    TEST_ASSERT_INT_EQ((int)window[0], 210);
    TEST_ASSERT_INT_EQ((int)window[1], 211);
}

/*
 * 25 samples into window_size=10: fills twice (samples[0..9], samples[10..19]),
 * 5 remain.
 * Returns 2, *pos == 5.
 */
static void test_accumulate_two_fills(void)
{
    uint16_t window[10];
    uint16_t snapshot[10];
    int pos = 0;

    uint16_t samples[25];
    for (int i = 0; i < 25; i++) {
        samples[i] = (uint16_t)(300 + i);
    }

    int fills = window_accumulate(window, 10, &pos, samples, 25, snapshot);

    TEST_ASSERT_INT_EQ(fills, 2);
    TEST_ASSERT_INT_EQ(pos, 5);
    /* Verify the partial next-window state: window[0..4] = samples[20..24] */
    TEST_ASSERT_INT_EQ((int)window[0], 320);
    TEST_ASSERT_INT_EQ((int)window[4], 324);
}

/*
 * Carry-over state: two successive calls with shared pos.
 *   Call 1: 8 samples into window_size=10 → 0 fills, *pos=8
 *   Call 2: 4 more samples → window fills once (samples 8-9 from call 1
 *            plus samples 0-1 from call 2), then 2 remain.
 *           → 1 fill, *pos=2
 */
static void test_accumulate_carry_over(void)
{
    uint16_t window[10];
    uint16_t snapshot[10];
    int pos = 0;

    /* Call 1: 8 samples, no fill */
    uint16_t batch1[8];
    for (int i = 0; i < 8; i++) {
        batch1[i] = (uint16_t)(400 + i);
    }
    int fills1 = window_accumulate(window, 10, &pos, batch1, 8, snapshot);

    TEST_ASSERT_INT_EQ(fills1, 0);
    TEST_ASSERT_INT_EQ(pos, 8);

    /* Call 2: 4 more samples, completing the window and starting the next */
    uint16_t batch2[4];
    for (int i = 0; i < 4; i++) {
        batch2[i] = (uint16_t)(500 + i);
    }
    int fills2 = window_accumulate(window, 10, &pos, batch2, 4, snapshot);

    TEST_ASSERT_INT_EQ(fills2, 1);
    TEST_ASSERT_INT_EQ(pos, 2);
    /* The snapshot should contain the 10-sample window:
     * batch1[0..7] then batch2[0..1] */
    for (int i = 0; i < 8; i++) {
        TEST_ASSERT_INT_EQ((int)snapshot[i], 400 + i);
    }
    TEST_ASSERT_INT_EQ((int)snapshot[8], 500);
    TEST_ASSERT_INT_EQ((int)snapshot[9], 501);
}

/*
 * snapshot=NULL: must not crash when the window fills.
 * Returns 1, *pos == 0.
 */
static void test_accumulate_snapshot_null(void)
{
    uint16_t window[10];
    int pos = 0;

    uint16_t samples[10];
    for (int i = 0; i < 10; i++) {
        samples[i] = (uint16_t)(600 + i);
    }

    int fills = window_accumulate(window, 10, &pos, samples, 10, NULL);

    TEST_ASSERT_INT_EQ(fills, 1);
    TEST_ASSERT_INT_EQ(pos, 0);
    /* Verify the window was actually written even though snapshot is NULL */
    TEST_ASSERT_INT_EQ((int)window[0], 600);
    TEST_ASSERT_INT_EQ((int)window[9], 609);
}

/*
 * 0 samples: must return 0 and leave *pos unchanged.
 */
static void test_accumulate_empty_input(void)
{
    uint16_t window[10];
    int pos = 3;  /* pre-set to verify it is not modified */

    int fills = window_accumulate(window, 10, &pos, NULL, 0, NULL);

    TEST_ASSERT_INT_EQ(fills, 0);
    TEST_ASSERT_INT_EQ(pos, 3);
}

/* =========================================================================
 * main
 * ========================================================================= */

int main(void)
{
    /* adc_parse_frame */
    RUN_TEST(test_parse_known_values);
    RUN_TEST(test_parse_with_channel_bits);
    RUN_TEST(test_parse_partial_frame);
    RUN_TEST(test_parse_zero_length);
    RUN_TEST(test_parse_max_out_limit);

    /* window_accumulate */
    RUN_TEST(test_accumulate_partial_fill);
    RUN_TEST(test_accumulate_exact_fill);
    RUN_TEST(test_accumulate_overfill);
    RUN_TEST(test_accumulate_two_fills);
    RUN_TEST(test_accumulate_carry_over);
    RUN_TEST(test_accumulate_snapshot_null);
    RUN_TEST(test_accumulate_empty_input);

    return TEST_REPORT();
}
