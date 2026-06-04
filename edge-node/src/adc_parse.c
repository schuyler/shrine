#include "adc_parse.h"

#include <string.h>

int adc_parse_frame(const uint8_t *raw, int raw_len,
                    uint16_t *out, int max_out)
{
    if (raw == NULL || out == NULL || raw_len <= 0 || max_out <= 0) {
        return 0;
    }

    int n_available = raw_len / 2;
    int n_to_parse = n_available < max_out ? n_available : max_out;

    for (int i = 0; i < n_to_parse; i++) {
        uint16_t word = (uint16_t)(raw[i * 2] | ((uint16_t)raw[i * 2 + 1] << 8));
        out[i] = word & 0x0FFFu;
    }

    return n_to_parse;
}

int window_accumulate(uint16_t *window, int window_size, int *pos,
                      const uint16_t *samples, int n_samples,
                      uint16_t *snapshot)
{
    int fills = 0;

    for (int i = 0; i < n_samples; i++) {
        window[*pos] = samples[i];
        (*pos)++;

        if (*pos == window_size) {
            if (snapshot != NULL) {
                memcpy(snapshot, window, (size_t)window_size * sizeof(uint16_t));
            }
            *pos = 0;
            fills++;
        }
    }

    return fills;
}
