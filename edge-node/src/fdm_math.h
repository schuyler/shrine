#ifndef FDM_MATH_H
#define FDM_MATH_H

#include <stdint.h>

// I/Q demodulation at a single DFT bin using incremental NCO rotation
// with internal DC removal (mean subtraction) and renormalization every
// 64 samples. Operates on raw samples — do not pre-subtract mean.
// cos_step = cos(2*PI*k/N), sin_step = -sin(2*PI*k/N) (DFT convention)
// Returns magnitude (sqrt(I^2 + Q^2) / n_samples)
float fdm_demod_magnitude(const uint16_t *samples, int n_samples,
                           float cos_step, float sin_step);

// Compute population stdev of raw uint16_t samples after DC removal (subtract mean).
// Used as self-cap presence metric. Returns 0 for constant input.
float fdm_stdev(const uint16_t *samples, int n_samples);

// Fill gsr_node[] with the (node_id+offset)%num_nodes convention
// gsr_node must have at least (num_nodes - 1) elements
void fdm_gsr_ordering(uint8_t node_id, uint8_t num_nodes, uint8_t *gsr_node);

// Precompute Hann window coefficients: out[i] = 0.5*(1 - cos(2*PI*i/(n-1)))
void fdm_hann_window(float *out, int n);

// In-place radix-2 Cooley-Tukey FFT on interleaved complex data.
// data[] has 2*n elements: [re0, im0, re1, im1, ...].
// n must be a power of 2.
void fdm_fft_radix2(float *data, int n);

// Compute log-magnitude spectrum from FFT output.
// fft_data[] is interleaved complex (2*n floats), n is the FFT size.
// out[] receives n/2 uint8_t values (DC to Nyquist).
// Mapping: 96 dB dynamic range, 0 = noise floor, 255 = full scale.
void fdm_fft_log_magnitudes(const float *fft_data, int n, uint8_t *out);

#endif /* FDM_MATH_H */
