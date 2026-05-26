/**
 * test_tdm.c — Host-side unit tests for the TDM module.
 *
 * Compiled and run on the host (not on the ESP32).  The build must stub out
 * esp_log.h (or provide a no-op implementation) so that tdm.c can be linked
 * without the IDF.
 *
 * Test harness: test_utils.h (minimal, provided separately).
 *   TEST_ASSERT(cond)
 *   TEST_ASSERT_FLOAT_NEAR(a, b, tol)
 *   TEST_ASSERT_INT_EQ(a, b)
 *   RUN_TEST(func)
 *   TEST_REPORT()  → returns 0 on all-pass
 */

#include "test_utils.h"
#include "../src/tdm.h"
#include "../src/config.h"

#include <math.h>
#include <stdint.h>
#include <stdbool.h>

/* =========================================================================
 * Helpers
 * ========================================================================= */

#ifndef M_PI
#define M_PI 3.14159265358979323846
#endif

/* =========================================================================
 * Slot schedule tests
 * ========================================================================= */

/* Slots 0-3: self-cap, tx_node == rx_node == slot_index, is_gsr == false */
static void test_self_cap_slots(void)
{
    const tdm_slot_t *sched = tdm_get_schedule(false);

    for (int i = 0; i < 4; i++) {
        TEST_ASSERT_INT_EQ((int)sched[i].tx_node, i);
        TEST_ASSERT_INT_EQ((int)sched[i].rx_node, i);
        TEST_ASSERT(sched[i].is_gsr == false);
    }
}

/* Slots 4-9: GSR pairs with correct (tx, rx) values and is_gsr == true */
static void test_gsr_slots(void)
{
    const tdm_slot_t *sched = tdm_get_schedule(false);

    /* Expected (tx, rx) for slots 4-9 */
    static const uint8_t expected_tx[6] = { 0, 0, 0, 1, 1, 2 };
    static const uint8_t expected_rx[6] = { 1, 2, 3, 2, 3, 3 };

    for (int i = 0; i < 6; i++) {
        int slot = i + 4;
        TEST_ASSERT(sched[slot].is_gsr == true);
        TEST_ASSERT_INT_EQ((int)sched[slot].tx_node, (int)expected_tx[i]);
        TEST_ASSERT_INT_EQ((int)sched[slot].rx_node, (int)expected_rx[i]);
    }
}

/* All TX and RX values must be in range 0-3 */
static void test_slot_node_ids_in_range(void)
{
    const tdm_slot_t *sched = tdm_get_schedule(false);

    for (int i = 0; i < TDM_SLOTS; i++) {
        TEST_ASSERT(sched[i].tx_node <= 3);
        TEST_ASSERT(sched[i].rx_node <= 3);
    }
}

/* =========================================================================
 * GSR mapping tests
 * ========================================================================= */

/*
 * Node 0 is never an RX node in any GSR slot, so every GSR slot should
 * return -1, and self-cap slots should also return -1.
 */
static void test_gsr_mapping_node0(void)
{
    tdm_init_gsr_mapping(0, tdm_get_schedule(false), TDM_SLOTS);

    /* self-cap slots */
    for (int i = 0; i < 4; i++) {
        TEST_ASSERT_INT_EQ(tdm_gsr_result_index((uint8_t)i), -1);
    }

    /* GSR slots — node 0 is TX only, never RX */
    for (int i = 4; i < TDM_SLOTS; i++) {
        TEST_ASSERT_INT_EQ(tdm_gsr_result_index((uint8_t)i), -1);
    }
}

/*
 * Node 1 is RX only in slot 4 → gsr_result index 0.
 * All other slots return -1.
 */
static void test_gsr_mapping_node1(void)
{
    tdm_init_gsr_mapping(1, tdm_get_schedule(false), TDM_SLOTS);

    /* self-cap slots */
    for (int i = 0; i < 4; i++) {
        TEST_ASSERT_INT_EQ(tdm_gsr_result_index((uint8_t)i), -1);
    }

    /* slot 4: RX → index 0 */
    TEST_ASSERT_INT_EQ(tdm_gsr_result_index(4), 0);

    /* slots 5-9: not RX */
    TEST_ASSERT_INT_EQ(tdm_gsr_result_index(5), -1);
    TEST_ASSERT_INT_EQ(tdm_gsr_result_index(6), -1);
    TEST_ASSERT_INT_EQ(tdm_gsr_result_index(7), -1);
    TEST_ASSERT_INT_EQ(tdm_gsr_result_index(8), -1);
    TEST_ASSERT_INT_EQ(tdm_gsr_result_index(9), -1);
}

/*
 * Node 2 is RX in slots 5 and 7 → gsr_result indices 0 and 1.
 * All other slots return -1.
 */
static void test_gsr_mapping_node2(void)
{
    tdm_init_gsr_mapping(2, tdm_get_schedule(false), TDM_SLOTS);

    /* self-cap slots */
    for (int i = 0; i < 4; i++) {
        TEST_ASSERT_INT_EQ(tdm_gsr_result_index((uint8_t)i), -1);
    }

    /* slot 4: node 2 is not RX */
    TEST_ASSERT_INT_EQ(tdm_gsr_result_index(4), -1);
    /* slot 5: RX → index 0 */
    TEST_ASSERT_INT_EQ(tdm_gsr_result_index(5), 0);
    /* slot 6: not RX */
    TEST_ASSERT_INT_EQ(tdm_gsr_result_index(6), -1);
    /* slot 7: RX → index 1 */
    TEST_ASSERT_INT_EQ(tdm_gsr_result_index(7), 1);
    /* slots 8-9: not RX */
    TEST_ASSERT_INT_EQ(tdm_gsr_result_index(8), -1);
    TEST_ASSERT_INT_EQ(tdm_gsr_result_index(9), -1);
}

/*
 * Node 3 is RX in slots 6, 8, 9 → gsr_result indices 0, 1, 2.
 * All other slots return -1.
 */
static void test_gsr_mapping_node3(void)
{
    tdm_init_gsr_mapping(3, tdm_get_schedule(false), TDM_SLOTS);

    /* self-cap slots */
    for (int i = 0; i < 4; i++) {
        TEST_ASSERT_INT_EQ(tdm_gsr_result_index((uint8_t)i), -1);
    }

    /* slots 4-5: not RX */
    TEST_ASSERT_INT_EQ(tdm_gsr_result_index(4), -1);
    TEST_ASSERT_INT_EQ(tdm_gsr_result_index(5), -1);
    /* slot 6: RX → index 0 */
    TEST_ASSERT_INT_EQ(tdm_gsr_result_index(6), 0);
    /* slot 7: not RX */
    TEST_ASSERT_INT_EQ(tdm_gsr_result_index(7), -1);
    /* slot 8: RX → index 1 */
    TEST_ASSERT_INT_EQ(tdm_gsr_result_index(8), 1);
    /* slot 9: RX → index 2 */
    TEST_ASSERT_INT_EQ(tdm_gsr_result_index(9), 2);
}

/*
 * Self-cap slots (0-3) always return -1 regardless of which node is active.
 * Re-verify after cycling through all four node IDs.
 */
static void test_self_cap_slots_always_minus1(void)
{
    for (uint8_t node = 0; node < 4; node++) {
        tdm_init_gsr_mapping(node, tdm_get_schedule(false), TDM_SLOTS);
        for (int slot = 0; slot < 4; slot++) {
            TEST_ASSERT_INT_EQ(tdm_gsr_result_index((uint8_t)slot), -1);
        }
    }
}

/* =========================================================================
 * Standalone schedule tests
 * ========================================================================= */

/* Standalone schedule: 2 slots */
static void test_standalone_slot_count(void)
{
    TEST_ASSERT_INT_EQ(tdm_get_slot_count(true), 2);
    TEST_ASSERT_INT_EQ(tdm_get_slot_count(false), TDM_SLOTS);
}

/* Standalone slot 0: self-cap (tx=0, rx=0, is_gsr=false) */
/* Standalone slot 1: loopback GSR (tx=0, rx=0, is_gsr=true) */
static void test_standalone_schedule(void)
{
    const tdm_slot_t *sched = tdm_get_schedule(true);

    TEST_ASSERT_INT_EQ((int)sched[0].tx_node, 0);
    TEST_ASSERT_INT_EQ((int)sched[0].rx_node, 0);
    TEST_ASSERT(sched[0].is_gsr == false);

    TEST_ASSERT_INT_EQ((int)sched[1].tx_node, 0);
    TEST_ASSERT_INT_EQ((int)sched[1].rx_node, 0);
    TEST_ASSERT(sched[1].is_gsr == true);
}

/* In standalone mode, node 0 has 1 GSR RX slot (slot 1) → gsr_result[0] */
static void test_gsr_mapping_standalone_node0(void)
{
    const tdm_slot_t *sched = tdm_get_schedule(true);
    int n_slots = tdm_get_slot_count(true);
    tdm_init_gsr_mapping(0, sched, n_slots);

    /* slot 0: self-cap, not GSR → -1 */
    TEST_ASSERT_INT_EQ(tdm_gsr_result_index(0), -1);

    /* slot 1: loopback GSR, node 0 is RX → gsr_result[0] */
    TEST_ASSERT_INT_EQ(tdm_gsr_result_index(1), 0);
}

/* =========================================================================
 * I/Q demodulation tests
 * ========================================================================= */

/*
 * DC input: all samples = 2048 (the midpoint).
 * After DC removal every sample is 0, so magnitude must be ~0.
 */
static void test_demod_dc_input(void)
{
    uint16_t samples[40];
    for (int i = 0; i < 40; i++) {
        samples[i] = 2048;
    }

    float mag = -1.0f, phase = -1.0f;
    tdm_demod_iq(samples, 40, &mag, &phase);

    TEST_ASSERT_FLOAT_NEAR(mag, 0.0f, 0.001f);
}

/*
 * Pure cosine at the fundamental frequency:
 *   samples[n] = 2048 + A * cos(2π n / 5)
 *
 * Analysis:
 *   After DC removal s[n] = A*cos(2πn/5).
 *   Over one full cycle (5 samples):
 *     I_acc = A * Σ cos²(2πk/5) = A * 2.5
 *     Q_acc = A * Σ cos(2πk/5)*sin(2πk/5) = 0
 *   mag = sqrt(I²+Q²) / n_samples = A*2.5 / 5 = A/2
 *   phase = atan2(0, positive) = 0
 *
 * For N cycles the result is identical (each cycle contributes equally).
 */
static void test_demod_pure_cosine(void)
{
    const int    N       = 5;       /* one full cycle */
    const float  A       = 1000.0f;
    const float  EXPECT_MAG   = A / 2.0f;   /* 500.0 */
    const float  EXPECT_PHASE = 0.0f;

    uint16_t samples[N];
    for (int n = 0; n < N; n++) {
        samples[n] = (uint16_t)(2048.0f + A * cosf(2.0f * (float)M_PI * n / 5.0f));
    }

    float mag, phase;
    tdm_demod_iq(samples, N, &mag, &phase);

    TEST_ASSERT_FLOAT_NEAR(mag,   EXPECT_MAG,   EXPECT_MAG * 0.01f);
    TEST_ASSERT_FLOAT_NEAR(phase, EXPECT_PHASE, 0.05f);
}

/*
 * Pure sine at the fundamental frequency:
 *   samples[n] = 2048 + A * sin(2π n / 5)
 *
 * Analysis:
 *   I_acc = A * Σ sin(2πk/5)*cos(2πk/5) = 0
 *   Q_acc = A * Σ sin²(2πk/5) = A * 2.5
 *   mag   = A/2
 *   phase = atan2(positive, 0) = π/2
 */
static void test_demod_pure_sine(void)
{
    const int    N       = 5;
    const float  A       = 1000.0f;
    const float  EXPECT_MAG   = A / 2.0f;
    const float  EXPECT_PHASE = (float)(M_PI / 2.0);

    uint16_t samples[N];
    for (int n = 0; n < N; n++) {
        samples[n] = (uint16_t)(2048.0f + A * sinf(2.0f * (float)M_PI * n / 5.0f));
    }

    float mag, phase;
    tdm_demod_iq(samples, N, &mag, &phase);

    TEST_ASSERT_FLOAT_NEAR(mag,   EXPECT_MAG,   EXPECT_MAG * 0.01f);
    TEST_ASSERT_FLOAT_NEAR(phase, EXPECT_PHASE, 0.05f);
}

/*
 * Multi-cycle known sinusoid: 40 samples (8 full cycles) of a cosine.
 *
 *   samples[n] = 2048 + A * cos(2π n / 5)
 *
 * Because N=40 is a multiple of 5, the result is exactly A/2 and phase=0.
 * Tolerances are tighter than the single-cycle test because averaging over
 * more cycles reduces floating-point rounding.
 */
static void test_demod_multi_cycle(void)
{
    const int    N       = 40;
    const float  A       = 1000.0f;
    const float  EXPECT_MAG   = A / 2.0f;
    const float  EXPECT_PHASE = 0.0f;

    uint16_t samples[40];
    for (int n = 0; n < N; n++) {
        samples[n] = (uint16_t)(2048.0f + A * cosf(2.0f * (float)M_PI * n / 5.0f));
    }

    float mag, phase;
    tdm_demod_iq(samples, N, &mag, &phase);

    TEST_ASSERT_FLOAT_NEAR(mag,   EXPECT_MAG,   EXPECT_MAG * 0.01f);
    TEST_ASSERT_FLOAT_NEAR(phase, EXPECT_PHASE, 0.05f);
}

/*
 * Zero input: all samples = 0.
 *
 * After DC removal every sample becomes -2048.  Over a multiple of 5
 * samples the cosine and sine sums each cancel to zero (orthogonality),
 * so mag = 0.  The test verifies:
 *   1. No crash or undefined behavior.
 *   2. mag is finite (not NaN or Inf).
 *   3. mag is ~0.
 */
static void test_demod_zero_input(void)
{
    uint16_t samples[40];
    for (int i = 0; i < 40; i++) {
        samples[i] = 0;
    }

    float mag = -1.0f, phase = -1.0f;
    tdm_demod_iq(samples, 40, &mag, &phase);

    /* must be finite */
    TEST_ASSERT(mag == mag);       /* NaN check: NaN != NaN */
    TEST_ASSERT(phase == phase);

    /* Over 40 samples (8 full cycles) the -2048 DC component cancels out */
    TEST_ASSERT_FLOAT_NEAR(mag, 0.0f, 0.001f);
}

/* =========================================================================
 * main
 * ========================================================================= */

int main(void)
{
    /* Slot schedule */
    RUN_TEST(test_self_cap_slots);
    RUN_TEST(test_gsr_slots);
    RUN_TEST(test_slot_node_ids_in_range);

    /* GSR mapping */
    RUN_TEST(test_gsr_mapping_node0);
    RUN_TEST(test_gsr_mapping_node1);
    RUN_TEST(test_gsr_mapping_node2);
    RUN_TEST(test_gsr_mapping_node3);
    RUN_TEST(test_self_cap_slots_always_minus1);

    /* Standalone */
    RUN_TEST(test_standalone_slot_count);
    RUN_TEST(test_standalone_schedule);
    RUN_TEST(test_gsr_mapping_standalone_node0);

    /* I/Q demodulation */
    RUN_TEST(test_demod_dc_input);
    RUN_TEST(test_demod_pure_cosine);
    RUN_TEST(test_demod_pure_sine);
    RUN_TEST(test_demod_multi_cycle);
    RUN_TEST(test_demod_zero_input);

    return TEST_REPORT();
}
