/*
 * test_tinyosc.c — host-side unit tests for the tinyosc OSC library
 *
 * Build and run on the host (no embedded target required).
 * Depends on test_utils.h for the minimal test harness.
 */

#include "test_utils.h"
#include "../components/tinyosc/tinyosc.h"

#include <stdint.h>
#include <string.h>

/* -------------------------------------------------------------------------
 * Helpers
 * ------------------------------------------------------------------------- */

/* Extract the big-endian byte representation of a float without UB. */
static void float_to_be_bytes(float f, uint8_t out[4])
{
    uint32_t bits;
    memcpy(&bits, &f, sizeof(bits));
    out[0] = (uint8_t)((bits >> 24) & 0xFF);
    out[1] = (uint8_t)((bits >> 16) & 0xFF);
    out[2] = (uint8_t)((bits >>  8) & 0xFF);
    out[3] = (uint8_t)( bits        & 0xFF);
}

/* -------------------------------------------------------------------------
 * Address padding tests
 * ------------------------------------------------------------------------- */

/*
 * "/a" has strlen 2, so the string with NUL is 3 bytes.
 * pad4(3) == 4.  Buffer should contain '/','a','\0','\0'.
 */
static void test_address_padding_short(void)
{
    char buf[64];
    memset(buf, 0xAA, sizeof(buf));
    int ret = tosc_writeMessage(buf, sizeof(buf), "/a", "f", 0.0f);
    TEST_ASSERT(ret > 0);
    /* Address occupies bytes [0,3]. */
    TEST_ASSERT(buf[0] == '/');
    TEST_ASSERT(buf[1] == 'a');
    TEST_ASSERT(buf[2] == '\0');
    TEST_ASSERT(buf[3] == '\0');  /* padding byte must be zero */
}

/*
 * "/ab" has strlen 3, so the string with NUL is 4 bytes.
 * pad4(4) == 4.  No extra padding needed; byte 3 is the NUL terminator.
 */
static void test_address_padding_exact_boundary(void)
{
    char buf[64];
    memset(buf, 0xAA, sizeof(buf));
    int ret = tosc_writeMessage(buf, sizeof(buf), "/ab", "f", 0.0f);
    TEST_ASSERT(ret > 0);
    TEST_ASSERT(buf[0] == '/');
    TEST_ASSERT(buf[1] == 'a');
    TEST_ASSERT(buf[2] == 'b');
    TEST_ASSERT(buf[3] == '\0');
}

/*
 * "/shrine/node/0" has strlen 14, so the string with NUL is 15 bytes.
 * pad4(15) == 16.  Byte 15 must be a zero padding byte.
 */
static void test_address_padding_long(void)
{
    char buf[128];
    memset(buf, 0xAA, sizeof(buf));
    int ret = tosc_writeMessage(buf, sizeof(buf), "/shrine/node/0", "f", 0.0f);
    TEST_ASSERT(ret > 0);
    /* Spot-check the address content. */
    TEST_ASSERT(buf[0] == '/');
    TEST_ASSERT(buf[13] == '0');
    TEST_ASSERT(buf[14] == '\0');  /* NUL terminator */
    TEST_ASSERT(buf[15] == '\0'); /* padding byte must be zero */
}

/* -------------------------------------------------------------------------
 * Type tag formatting tests
 * ------------------------------------------------------------------------- */

/*
 * For format "f":
 *   type tag string is ",f" (3 bytes with NUL), pad4(3) == 4.
 *   Address "/a" occupies bytes [0,3], so type tag starts at offset 4.
 */
static void test_type_tag_single_f(void)
{
    char buf[64];
    memset(buf, 0xAA, sizeof(buf));
    int ret = tosc_writeMessage(buf, sizeof(buf), "/a", "f", 0.0f);
    TEST_ASSERT(ret > 0);
    int tag_off = 4; /* pad4(strlen("/a")+1) = pad4(3) = 4 */
    TEST_ASSERT(buf[tag_off + 0] == ',');
    TEST_ASSERT(buf[tag_off + 1] == 'f');
    TEST_ASSERT(buf[tag_off + 2] == '\0');
    TEST_ASSERT(buf[tag_off + 3] == '\0'); /* padding byte */
}

/*
 * For format "ff":
 *   type tag string is ",ff" (4 bytes with NUL), pad4(4) == 4.
 *   Byte 3 of the tag field is the NUL terminator, no extra padding.
 */
static void test_type_tag_two_f(void)
{
    char buf[64];
    memset(buf, 0xAA, sizeof(buf));
    int ret = tosc_writeMessage(buf, sizeof(buf), "/a", "ff", 0.0f, 0.0f);
    TEST_ASSERT(ret > 0);
    int tag_off = 4;
    TEST_ASSERT(buf[tag_off + 0] == ',');
    TEST_ASSERT(buf[tag_off + 1] == 'f');
    TEST_ASSERT(buf[tag_off + 2] == 'f');
    TEST_ASSERT(buf[tag_off + 3] == '\0');
}

/*
 * For format "fffffff" (7 floats — the MiniCAT use case):
 *   type tag string is ",fffffff" (9 bytes with NUL), pad4(9) == 12.
 *   Bytes 9–11 of the tag field must be zero padding.
 */
static void test_type_tag_seven_f(void)
{
    char buf[128];
    memset(buf, 0xAA, sizeof(buf));
    int ret = tosc_writeMessage(buf, sizeof(buf), "/a", "fffffff",
                                0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f);
    TEST_ASSERT(ret > 0);
    int tag_off = 4;
    TEST_ASSERT(buf[tag_off + 0] == ',');
    TEST_ASSERT(buf[tag_off + 1] == 'f');
    TEST_ASSERT(buf[tag_off + 7] == 'f'); /* last 'f' */
    TEST_ASSERT(buf[tag_off + 8] == '\0');
    TEST_ASSERT(buf[tag_off + 9]  == '\0'); /* padding */
    TEST_ASSERT(buf[tag_off + 10] == '\0'); /* padding */
    TEST_ASSERT(buf[tag_off + 11] == '\0'); /* padding */
}

/* -------------------------------------------------------------------------
 * Float encoding tests
 * ------------------------------------------------------------------------- */

/*
 * 0.0f is all-zeros in IEEE 754.
 */
static void test_float_encoding_zero(void)
{
    char buf[64];
    int ret = tosc_writeMessage(buf, sizeof(buf), "/a", "f", 0.0f);
    TEST_ASSERT(ret > 0);
    /* Address 4 bytes + type tag 4 bytes = float at offset 8. */
    int foff = 8;
    TEST_ASSERT((unsigned char)buf[foff + 0] == 0x00);
    TEST_ASSERT((unsigned char)buf[foff + 1] == 0x00);
    TEST_ASSERT((unsigned char)buf[foff + 2] == 0x00);
    TEST_ASSERT((unsigned char)buf[foff + 3] == 0x00);
}

/*
 * 1.0f == 0x3F800000 in IEEE 754.
 */
static void test_float_encoding_one(void)
{
    char buf[64];
    int ret = tosc_writeMessage(buf, sizeof(buf), "/a", "f", 1.0f);
    TEST_ASSERT(ret > 0);
    int foff = 8;
    TEST_ASSERT((unsigned char)buf[foff + 0] == 0x3F);
    TEST_ASSERT((unsigned char)buf[foff + 1] == 0x80);
    TEST_ASSERT((unsigned char)buf[foff + 2] == 0x00);
    TEST_ASSERT((unsigned char)buf[foff + 3] == 0x00);
}

/*
 * -1.0f == 0xBF800000 in IEEE 754.
 */
static void test_float_encoding_neg_one(void)
{
    char buf[64];
    int ret = tosc_writeMessage(buf, sizeof(buf), "/a", "f", -1.0f);
    TEST_ASSERT(ret > 0);
    int foff = 8;
    TEST_ASSERT((unsigned char)buf[foff + 0] == 0xBF);
    TEST_ASSERT((unsigned char)buf[foff + 1] == 0x80);
    TEST_ASSERT((unsigned char)buf[foff + 2] == 0x00);
    TEST_ASSERT((unsigned char)buf[foff + 3] == 0x00);
}

/*
 * 3.14159f: derive expected bytes at runtime to avoid manual bit-pattern
 * errors, then confirm the implementation produces the same bytes.
 */
static void test_float_encoding_pi_approx(void)
{
    char buf[64];
    float val = 3.14159f;
    int ret = tosc_writeMessage(buf, sizeof(buf), "/a", "f", val);
    TEST_ASSERT(ret > 0);
    int foff = 8;
    uint8_t expected[4];
    float_to_be_bytes(val, expected);
    TEST_ASSERT((unsigned char)buf[foff + 0] == expected[0]);
    TEST_ASSERT((unsigned char)buf[foff + 1] == expected[1]);
    TEST_ASSERT((unsigned char)buf[foff + 2] == expected[2]);
    TEST_ASSERT((unsigned char)buf[foff + 3] == expected[3]);
}

/* -------------------------------------------------------------------------
 * Full message integration test
 *
 * tosc_writeMessage(buf, sizeof(buf), "/shrine/node/0", "fffffff",
 *                   1.0f, 2.0f, 3.0f, 4.0f, 5.0f, 6.0f, 7.0f)
 *
 * Expected layout:
 *   [0  .. 15]  address "/shrine/node/0"  pad4(15) = 16 bytes
 *   [16 .. 27]  type tag ",fffffff"       pad4(9)  = 12 bytes
 *   [28 .. 31]  float 1.0f
 *   [32 .. 35]  float 2.0f
 *   [36 .. 39]  float 3.0f
 *   [40 .. 43]  float 4.0f
 *   [44 .. 47]  float 5.0f
 *   [48 .. 51]  float 6.0f
 *   [52 .. 55]  float 7.0f
 *   Total: 56 bytes
 * ------------------------------------------------------------------------- */

static void test_full_message_return_value(void)
{
    char buf[128];
    int ret = tosc_writeMessage(buf, sizeof(buf), "/shrine/node/0", "fffffff",
                                1.0f, 2.0f, 3.0f, 4.0f, 5.0f, 6.0f, 7.0f);
    TEST_ASSERT_INT_EQ(56, ret);
}

static void test_full_message_address_bytes(void)
{
    char buf[128];
    memset(buf, 0xAA, sizeof(buf));
    int ret = tosc_writeMessage(buf, sizeof(buf), "/shrine/node/0", "fffffff",
                                1.0f, 2.0f, 3.0f, 4.0f, 5.0f, 6.0f, 7.0f);
    TEST_ASSERT(ret == 56);
    /* Address field: "/shrine/node/0\0" followed by one padding zero. */
    const char *addr = "/shrine/node/0";
    for (int i = 0; i < 14; i++) {
        TEST_ASSERT(buf[i] == addr[i]);
    }
    TEST_ASSERT(buf[14] == '\0'); /* NUL terminator */
    TEST_ASSERT(buf[15] == '\0'); /* padding zero */
}

static void test_full_message_type_tag_bytes(void)
{
    char buf[128];
    memset(buf, 0xAA, sizeof(buf));
    int ret = tosc_writeMessage(buf, sizeof(buf), "/shrine/node/0", "fffffff",
                                1.0f, 2.0f, 3.0f, 4.0f, 5.0f, 6.0f, 7.0f);
    TEST_ASSERT(ret == 56);
    /* Type tag field starts at offset 16. */
    TEST_ASSERT(buf[16] == ',');
    TEST_ASSERT(buf[17] == 'f');
    TEST_ASSERT(buf[18] == 'f');
    TEST_ASSERT(buf[19] == 'f');
    TEST_ASSERT(buf[20] == 'f');
    TEST_ASSERT(buf[21] == 'f');
    TEST_ASSERT(buf[22] == 'f');
    TEST_ASSERT(buf[23] == 'f');
    TEST_ASSERT(buf[24] == '\0'); /* NUL terminator */
    TEST_ASSERT(buf[25] == '\0'); /* padding */
    TEST_ASSERT(buf[26] == '\0'); /* padding */
    TEST_ASSERT(buf[27] == '\0'); /* padding */
}

static void test_full_message_float_bytes(void)
{
    char buf[128];
    memset(buf, 0xAA, sizeof(buf));
    int ret = tosc_writeMessage(buf, sizeof(buf), "/shrine/node/0", "fffffff",
                                1.0f, 2.0f, 3.0f, 4.0f, 5.0f, 6.0f, 7.0f);
    TEST_ASSERT(ret == 56);

    float expected_vals[7] = {1.0f, 2.0f, 3.0f, 4.0f, 5.0f, 6.0f, 7.0f};
    int fbase = 28;
    for (int i = 0; i < 7; i++) {
        uint8_t expected[4];
        float_to_be_bytes(expected_vals[i], expected);
        int off = fbase + i * 4;
        TEST_ASSERT((unsigned char)buf[off + 0] == expected[0]);
        TEST_ASSERT((unsigned char)buf[off + 1] == expected[1]);
        TEST_ASSERT((unsigned char)buf[off + 2] == expected[2]);
        TEST_ASSERT((unsigned char)buf[off + 3] == expected[3]);
    }
}

/* -------------------------------------------------------------------------
 * Buffer overflow tests
 * ------------------------------------------------------------------------- */

/*
 * A 1-byte buffer cannot fit any OSC message; must return -1.
 */
static void test_overflow_tiny_buffer(void)
{
    char buf[1];
    buf[0] = (char)0xAA;
    int ret = tosc_writeMessage(buf, sizeof(buf), "/shrine/node/0", "fffffff",
                                1.0f, 2.0f, 3.0f, 4.0f, 5.0f, 6.0f, 7.0f);
    TEST_ASSERT_INT_EQ(-1, ret);
    /* Verify the single byte was not overwritten. */
    TEST_ASSERT((unsigned char)buf[0] == 0xAA);
}

/*
 * A buffer exactly one byte too small must return -1 and not write past
 * the end.  Sentinel bytes after the buffer must be undisturbed.
 */
static void test_overflow_one_byte_short(void)
{
    /*
     * The full message needs 56 bytes.  Allocate 57 bytes so that buf[55]
     * is a sentinel that should not be touched.
     */
    char buf[57];
    memset(buf, 0xBB, sizeof(buf));
    int ret = tosc_writeMessage(buf, 55 /* one short */, "/shrine/node/0",
                                "fffffff",
                                1.0f, 2.0f, 3.0f, 4.0f, 5.0f, 6.0f, 7.0f);
    TEST_ASSERT_INT_EQ(-1, ret);
    /* Sentinel at index 55 (outside the declared bufLen) must be untouched. */
    TEST_ASSERT((unsigned char)buf[55] == 0xBB);
    /* Sentinel at index 56 must also be untouched. */
    TEST_ASSERT((unsigned char)buf[56] == 0xBB);
}

/*
 * A zero-length buffer must return -1 immediately.
 */
static void test_overflow_zero_length_buffer(void)
{
    char buf[1];
    int ret = tosc_writeMessage(buf, 0, "/a", "f", 1.0f);
    TEST_ASSERT_INT_EQ(-1, ret);
}

/* -------------------------------------------------------------------------
 * Return value tests
 * ------------------------------------------------------------------------- */

/*
 * Return value equals the number of bytes written for various message sizes.
 *
 * "/a" "f": address pad4(3)=4, tag pad4(3)=4, 1 float=4 → 12 bytes
 */
static void test_return_value_single_float(void)
{
    char buf[64];
    int ret = tosc_writeMessage(buf, sizeof(buf), "/a", "f", 1.0f);
    TEST_ASSERT_INT_EQ(12, ret);
}

/*
 * "/a" "ff": address 4, tag pad4(4)=4, 2 floats=8 → 16 bytes
 */
static void test_return_value_two_floats(void)
{
    char buf[64];
    int ret = tosc_writeMessage(buf, sizeof(buf), "/a", "ff", 1.0f, 2.0f);
    TEST_ASSERT_INT_EQ(16, ret);
}

/*
 * Return value with a buffer exactly the right size must be positive (not -1).
 */
static void test_return_value_exact_fit(void)
{
    char buf[56];
    int ret = tosc_writeMessage(buf, sizeof(buf), "/shrine/node/0", "fffffff",
                                1.0f, 2.0f, 3.0f, 4.0f, 5.0f, 6.0f, 7.0f);
    TEST_ASSERT_INT_EQ(56, ret);
}

/* -------------------------------------------------------------------------
 * main
 * ------------------------------------------------------------------------- */

int main(void)
{
    RUN_TEST(test_address_padding_short);
    RUN_TEST(test_address_padding_exact_boundary);
    RUN_TEST(test_address_padding_long);

    RUN_TEST(test_type_tag_single_f);
    RUN_TEST(test_type_tag_two_f);
    RUN_TEST(test_type_tag_seven_f);

    RUN_TEST(test_float_encoding_zero);
    RUN_TEST(test_float_encoding_one);
    RUN_TEST(test_float_encoding_neg_one);
    RUN_TEST(test_float_encoding_pi_approx);

    RUN_TEST(test_full_message_return_value);
    RUN_TEST(test_full_message_address_bytes);
    RUN_TEST(test_full_message_type_tag_bytes);
    RUN_TEST(test_full_message_float_bytes);

    RUN_TEST(test_overflow_tiny_buffer);
    RUN_TEST(test_overflow_one_byte_short);
    RUN_TEST(test_overflow_zero_length_buffer);

    RUN_TEST(test_return_value_single_float);
    RUN_TEST(test_return_value_two_floats);
    RUN_TEST(test_return_value_exact_fit);

    return TEST_REPORT();
}
