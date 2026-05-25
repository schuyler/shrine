/*
 * tinyosc.c — minimal OSC message writer
 *
 * Implements OSC 1.0 wire format for messages with float arguments.
 * Only type tag 'f' (IEEE 754 32-bit float, big-endian) is supported.
 */

#include "tinyosc.h"

#include <stdint.h>
#include <string.h>
#include <stdarg.h>

/* Round up n to the next multiple of 4. */
static int pad4(int n)
{
    return (n + 3) & ~3;
}

/*
 * Write a null-terminated string into buf with 4-byte padding.
 * Returns the number of bytes written (always a multiple of 4), or -1 on
 * overflow.
 */
static int write_string(char *buf, int bufLen, const char *s)
{
    int slen = (int)strlen(s) + 1; /* include null terminator */
    int padded = pad4(slen);
    if (padded > bufLen) {
        return -1;
    }
    memcpy(buf, s, slen);
    /* zero-pad remaining bytes up to the 4-byte boundary */
    memset(buf + slen, 0, padded - slen);
    return padded;
}

/*
 * Write a 32-bit float as big-endian IEEE 754 into buf.
 * Returns 4, or -1 on overflow.
 */
static int write_float(char *buf, int bufLen, float f)
{
    if (bufLen < 4) {
        return -1;
    }
    uint32_t bits;
    memcpy(&bits, &f, sizeof(bits));
    buf[0] = (char)((bits >> 24) & 0xFF);
    buf[1] = (char)((bits >> 16) & 0xFF);
    buf[2] = (char)((bits >>  8) & 0xFF);
    buf[3] = (char)( bits        & 0xFF);
    return 4;
}

int tosc_writeMessage(char *buffer, int bufLen,
                      const char *address, const char *format, ...)
{
    int pos = 0;

    /* Write address pattern */
    int n = write_string(buffer + pos, bufLen - pos, address);
    if (n < 0) return -1;
    pos += n;

    /* Build type tag string: "," + format */
    char type_tag[64];
    int flen = (int)strlen(format);
    if (flen + 2 > (int)sizeof(type_tag)) return -1; /* comma + format + NUL */
    type_tag[0] = ',';
    memcpy(type_tag + 1, format, flen + 1); /* include NUL */

    n = write_string(buffer + pos, bufLen - pos, type_tag);
    if (n < 0) return -1;
    pos += n;

    /* Write arguments */
    va_list args;
    va_start(args, format);
    for (int i = 0; format[i] != '\0'; i++) {
        switch (format[i]) {
        case 'f': {
            /* va_arg promotes float to double; cast back */
            float f = (float)va_arg(args, double);
            n = write_float(buffer + pos, bufLen - pos, f);
            if (n < 0) {
                va_end(args);
                return -1;
            }
            pos += n;
            break;
        }
        default:
            /* Unsupported type tag — fail fast */
            va_end(args);
            return -1;
        }
    }
    va_end(args);

    return pos;
}
