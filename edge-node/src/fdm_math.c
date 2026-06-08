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

void fdm_hann_window(float *out, int n) {
    for (int i = 0; i < n; i++) {
        out[i] = 0.5f * (1.0f - cosf(2.0f * (float)M_PI * i / (n - 1)));
    }
}

void fdm_fft_radix2(float *data, int n) {
    /* Bit-reversal permutation */
    int bits = 0;
    int tmp = n;
    while (tmp > 1) { bits++; tmp >>= 1; }

    for (int i = 0; i < n; i++) {
        int rev = 0;
        int x = i;
        for (int b = 0; b < bits; b++) {
            rev = (rev << 1) | (x & 1);
            x >>= 1;
        }
        if (rev > i) {
            /* Swap complex elements at positions i and rev */
            float re_tmp = data[2*i];
            float im_tmp = data[2*i+1];
            data[2*i]     = data[2*rev];
            data[2*i+1]   = data[2*rev+1];
            data[2*rev]   = re_tmp;
            data[2*rev+1] = im_tmp;
        }
    }

    /* Butterfly stages */
    for (int s = 0; s < bits; s++) {
        int m = 2 << s;       /* butterfly size: 2, 4, 8, ..., n */
        int half = m / 2;
        for (int k = 0; k < half; k++) {
            float angle = -2.0f * (float)M_PI * k / m;
            float wr = cosf(angle);
            float wi = sinf(angle);
            for (int j = k; j < n; j += m) {
                float tr = wr * data[2*(j+half)] - wi * data[2*(j+half)+1];
                float ti = wr * data[2*(j+half)+1] + wi * data[2*(j+half)];
                data[2*(j+half)]   = data[2*j]   - tr;
                data[2*(j+half)+1] = data[2*j+1] - ti;
                data[2*j]   += tr;
                data[2*j+1] += ti;
            }
        }
    }
}

void fdm_fft_log_magnitudes(const float *fft_data, int n, uint8_t *out) {
    int half = n / 2;

    /* First pass: compute dB values and find max */
    float max_db = -1e30f;
    for (int i = 0; i < half; i++) {
        float re = fft_data[2*i];
        float im = fft_data[2*i+1];
        float mag = sqrtf(re*re + im*im);
        float db = 20.0f * log10f(mag + 1e-10f);
        if (db > max_db) max_db = db;
    }

    /* If max_db is below a minimum threshold, the entire frame is noise —
     * output all zeros rather than mapping relative to a meaningless peak. */
    if (max_db < -90.0f) {
        for (int i = 0; i < half; i++) out[i] = 0;
        return;
    }

    /* Second pass: quantize relative to max */
    float floor_db = max_db - 96.0f;
    for (int i = 0; i < half; i++) {
        float re = fft_data[2*i];
        float im = fft_data[2*i+1];
        float mag = sqrtf(re*re + im*im);
        float db = 20.0f * log10f(mag + 1e-10f);
        float val = (db - floor_db) * 255.0f / 96.0f;
        if (val < 0.0f)   val = 0.0f;
        if (val > 255.0f) val = 255.0f;
        out[i] = (uint8_t)val;
    }
}
