#ifndef TINYOSC_H
#define TINYOSC_H

/*
 * tinyosc — minimal OSC message writer
 *
 * Supports writing OSC messages with float ('f') arguments to a caller-
 * supplied buffer.  The wire format follows the OSC 1.0 spec:
 *   - address pattern:  null-terminated string, padded to 4-byte boundary
 *   - type tag string:  "," + type chars, null-terminated, padded to 4-byte boundary
 *   - arguments:        big-endian IEEE 754 floats (4 bytes each)
 */

#include <stdarg.h>

#ifdef __cplusplus
extern "C" {
#endif

/**
 * Write an OSC message into buffer.
 *
 * @param buffer   Destination buffer.
 * @param bufLen   Capacity of destination buffer in bytes.
 * @param address  OSC address pattern, e.g. "/shrine/cap".
 * @param format   Type tag string (without the leading comma), e.g. "fff".
 *                 Only 'f' (float) is currently supported.
 * @param ...      One float argument per character in format.
 *
 * @return Number of bytes written, or -1 if the buffer is too small.
 */
int tosc_writeMessage(char *buffer, int bufLen,
                      const char *address, const char *format, ...);

#ifdef __cplusplus
}
#endif

#endif /* TINYOSC_H */
