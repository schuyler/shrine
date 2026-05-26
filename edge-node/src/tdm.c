#include "tdm.h"
#include "config.h"

#include <math.h>
#include <string.h>
#include "esp_log.h"

static const char *TAG = "tdm";

/* -------------------------------------------------------------------------
 * Compile-time TDM schedule
 * -------------------------------------------------------------------------
 *
 * Slots 0–3: self-cap, tx=rx=slot_index
 * Slots 4–9: GSR pairs (tx,rx): (0,1),(0,2),(0,3),(1,2),(1,3),(2,3)
 */

static const tdm_slot_t s_schedule[TDM_SLOTS] = {
    /* slot 0 */ { .tx_node = 0, .rx_node = 0, .is_gsr = false },
    /* slot 1 */ { .tx_node = 1, .rx_node = 1, .is_gsr = false },
    /* slot 2 */ { .tx_node = 2, .rx_node = 2, .is_gsr = false },
    /* slot 3 */ { .tx_node = 3, .rx_node = 3, .is_gsr = false },
    /* slot 4 */ { .tx_node = 0, .rx_node = 1, .is_gsr = true  },
    /* slot 5 */ { .tx_node = 0, .rx_node = 2, .is_gsr = true  },
    /* slot 6 */ { .tx_node = 0, .rx_node = 3, .is_gsr = true  },
    /* slot 7 */ { .tx_node = 1, .rx_node = 2, .is_gsr = true  },
    /* slot 8 */ { .tx_node = 1, .rx_node = 3, .is_gsr = true  },
    /* slot 9 */ { .tx_node = 2, .rx_node = 3, .is_gsr = true  },
};

/* 2-slot standalone schedule: self-cap + loopback GSR, both on node 0 */
#define TDM_STANDALONE_SLOTS 2

static const tdm_slot_t s_schedule_standalone[TDM_STANDALONE_SLOTS] = {
    /* slot 0 */ { .tx_node = 0, .rx_node = 0, .is_gsr = false },
    /* slot 1 */ { .tx_node = 0, .rx_node = 0, .is_gsr = true  },
};

int tdm_get_slot_count(bool standalone)
{
    return standalone ? TDM_STANDALONE_SLOTS : TDM_SLOTS;
}

const tdm_slot_t *tdm_get_schedule(bool standalone)
{
    return standalone ? s_schedule_standalone : s_schedule;
}

/* -------------------------------------------------------------------------
 * GSR result mapping
 *
 * Each GSR RX node fills up to 3 result slots.  The mapping below is fixed
 * by the schedule above:
 *
 *   Node 0: RX in no GSR slots  → 0 entries
 *   Node 1: RX in slot 4        → gsr_result[0]
 *   Node 2: RX in slots 5, 7    → gsr_result[0], gsr_result[1]
 *   Node 3: RX in slots 6, 8, 9 → gsr_result[0], gsr_result[1], gsr_result[2]
 *
 * s_slot_to_gsr_index[i] is the gsr_result index for slot i if this node is
 * the RX for that slot, or -1 otherwise.
 */

static int8_t s_slot_to_gsr_index[TDM_SLOTS];

void tdm_init_gsr_mapping(uint8_t node_id, const tdm_slot_t *schedule,
                           int n_slots)
{
    if (n_slots > TDM_SLOTS) {
        ESP_LOGW(TAG, "n_slots %d exceeds TDM_SLOTS, clamping", n_slots);
        n_slots = TDM_SLOTS;
    }

    memset(s_slot_to_gsr_index, -1, sizeof(s_slot_to_gsr_index));

    int8_t result_idx = 0;
    for (int i = 0; i < n_slots; i++) {
        if (schedule[i].is_gsr && schedule[i].rx_node == node_id) {
            s_slot_to_gsr_index[i] = result_idx++;
        }
    }

    ESP_LOGI(TAG, "GSR mapping for node %u: %d RX slots", node_id,
             (int)result_idx);
}

int tdm_gsr_result_index(uint8_t slot_index)
{
    if (slot_index >= TDM_SLOTS) {
        return -1;
    }
    return s_slot_to_gsr_index[slot_index];
}

/* -------------------------------------------------------------------------
 * I/Q demodulation
 * -------------------------------------------------------------------------
 *
 * 5-point tables correspond to one excitation cycle sampled at exactly
 * SAMPLES_PER_CYCLE (5) equally-spaced points.
 */

static const float COS_TABLE[5] = { 1.0f,  0.3090f, -0.8090f, -0.8090f,  0.3090f };
static const float SIN_TABLE[5] = { 0.0f,  0.9511f,  0.5878f, -0.5878f, -0.9511f };

void tdm_demod_iq(const uint16_t *samples, int n_samples,
                  float *mag, float *phase)
{
    float i_acc = 0.0f;
    float q_acc = 0.0f;

    for (int n = 0; n < n_samples; n++) {
        float s = (float)samples[n] - 2048.0f;  /* remove 12-bit midpoint */
        int   t = n % 5;
        i_acc += s * COS_TABLE[t];
        q_acc += s * SIN_TABLE[t];
    }

    *mag   = sqrtf(i_acc * i_acc + q_acc * q_acc) / (float)n_samples;
    *phase = atan2f(q_acc, i_acc);
}
