#ifndef TDM_H
#define TDM_H

#include <stdint.h>
#include <stdbool.h>
#include "config.h"

/**
 * Describes one slot in the TDM frame.
 *
 * Slots 0–3: self-capacitance (tx_node == rx_node, is_gsr == false)
 * Slots 4–9: GSR pairs        (tx_node != rx_node, is_gsr == true)
 *
 *   Slot  tx  rx   GSR pair
 *     4    0   1   (0,1)
 *     5    0   2   (0,2)
 *     6    0   3   (0,3)
 *     7    1   2   (1,2)
 *     8    1   3   (1,3)
 *     9    2   3   (2,3)
 */
typedef struct {
    uint8_t tx_node;
    uint8_t rx_node;
    bool    is_gsr;
} tdm_slot_t;

/**
 * Return the number of slots in the TDM schedule.
 * @param standalone  true for the 2-slot standalone schedule.
 */
int tdm_get_slot_count(bool standalone);

/**
 * Return a pointer to the TDM schedule.
 * @param standalone  true for the 2-slot standalone schedule.
 */
const tdm_slot_t *tdm_get_schedule(bool standalone);

/**
 * Precompute which GSR result indices (0–2) this node populates.
 *
 * @param node_id   This node's ID (0–3).
 * @param schedule  Pointer to the TDM schedule array.
 * @param n_slots   Number of slots in the schedule.
 */
void tdm_init_gsr_mapping(uint8_t node_id, const tdm_slot_t *schedule,
                           int n_slots);

/**
 * Return the gsr_result index (0–2) for a given slot, or -1 if this node
 * is not the RX node for that slot.
 *
 * @param slot_index  TDM slot index (range depends on the active schedule).
 * @return            Index into scan_result_t.gsr_mag / .gsr_phase, or -1.
 */
int tdm_gsr_result_index(uint8_t slot_index);

/**
 * I/Q demodulation of a sample buffer.
 *
 * Uses 5-point cos/sin tables aligned with SAMPLES_PER_CYCLE.  Samples are
 * treated as 12-bit unsigned values; the 2048 midpoint is subtracted before
 * accumulation.
 *
 * @param samples    Array of 12-bit ADC samples.
 * @param n_samples  Number of samples (should be a multiple of 5 for best
 *                   accuracy, but any positive value works).
 * @param mag        Output: magnitude = sqrt(I²+Q²) / n_samples.
 * @param phase      Output: phase = atan2(Q, I) in radians.
 */
void tdm_demod_iq(const uint16_t *samples, int n_samples,
                  float *mag, float *phase);

#endif /* TDM_H */
