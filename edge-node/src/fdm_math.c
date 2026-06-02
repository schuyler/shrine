#include "fdm_math.h"
#include <math.h>

float fdm_demod_magnitude(const uint16_t *samples, int n_samples,
                           float cos_step, float sin_step) {
    /* DC removal: compute mean */
    float sum = 0.0f;
    for (int n = 0; n < n_samples; n++) {
        sum += (float)samples[n];
    }
    float mean = sum / (float)n_samples;

    /* NCO-based I/Q accumulation */
    float I = 0.0f, Q = 0.0f;
    float rc = 1.0f, rs = 0.0f;  /* NCO phasor: starts at angle 0 */

    for (int n = 0; n < n_samples; n++) {
        float x = (float)samples[n] - mean;
        I += x * rc;
        Q += x * rs;

        /* Rotate phasor by one step */
        float new_rc = rc * cos_step - rs * sin_step;
        float new_rs = rs * cos_step + rc * sin_step;
        rc = new_rc;
        rs = new_rs;

        /* Renormalize every 64 samples */
        if ((n + 1) % 64 == 0) {
            float norm = sqrtf(rc * rc + rs * rs);
            rc /= norm;
            rs /= norm;
        }
    }

    return sqrtf(I * I + Q * Q) / (float)n_samples;
}

float fdm_stdev(const uint16_t *samples, int n_samples) {
    /* Compute mean */
    float sum = 0.0f;
    for (int i = 0; i < n_samples; i++) {
        sum += (float)samples[i];
    }
    float mean = sum / (float)n_samples;

    /* Sum of squared deviations */
    float sum_sq = 0.0f;
    for (int i = 0; i < n_samples; i++) {
        float dev = (float)samples[i] - mean;
        sum_sq += dev * dev;
    }

    return sqrtf(sum_sq / (float)n_samples);
}

void fdm_gsr_ordering(uint8_t node_id, uint8_t num_nodes, uint8_t *gsr_node) {
    for (int offset = 1; offset < (int)num_nodes; offset++) {
        gsr_node[offset - 1] = (uint8_t)((node_id + offset) % num_nodes);
    }
}
