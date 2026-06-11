# Carrier-frequency override CSVs

These `nodeN.carrier.csv.example` files are a ready-to-flash NVS set for moving
the FDM carrier comb off an interferer (e.g. LED PWM harmonics landing in a
node's demod bin). They are normal NVS partition CSVs — the only difference from
`node.csv.example` is that they set the optional `base_k` / `step_k` / `window_n`
keys explicitly.

## What's different from the defaults

| Key | Firmware default | These CSVs |
|-----|------------------|-----------|
| `base_k` | 180 | **181** |
| `step_k` | 20 | **23** |
| `window_n` | 1800 | 1800 (unchanged, shown for tuning) |

The firmware default comb (bins 180/200/220/240) places all four carriers on
exact multiples of 2 kHz, so a PWM dimmer near a 2 kHz fundamental can drop a
harmonic on *every* node at once. This set uses an odd base and non-round
spacing so no single harmonic series rakes across the whole comb.

## Resulting carrier frequencies

The excitation frequency is computed at boot as `f_exc = k * fs / N`, where
`fs` is the measured ADC sample rate (~180 ksps) and `N = window_n`. With
`fs ≈ 180000` and `N = 1800` the bin width is 100 Hz:

| Node | bin `k = base_k + node_id*step_k` | f_exc (approx) |
|------|-----------------------------------|----------------|
| 0    | 181 | 18.1 kHz |
| 1    | 204 | 20.4 kHz |
| 2    | 227 | 22.7 kHz |
| 3    | 250 | 25.0 kHz |

(Absolute Hz drift slightly per boot because `f_exc` tracks the *measured* `fs`,
but the carriers stay locked to their bins, which is what the demodulator cares
about.)

## How to pick a different comb

1. **Survey first.** With the LEDs driven at worst case, plot each node's live
   spectrum: `scripts/plot_fft_osc.py` (nodes stream `/shrine/node/N/fft` every
   ~5 s). Find the quietest stretch.
2. Choose `base_k` (node 0's bin) to land node 0 in a clean gap, and `step_k`
   so the remaining three carriers also fall in clean gaps. Keep `step_k` near
   ~20 bins for crosstalk margin, and avoid round/harmonically-related values.
3. Constraints:
   - All bins must stay **below Nyquist**: `base_k + 3*step_k < N/2` (i.e. < 900
     at the default `N`).
   - **All four nodes must use the identical `base_k`/`step_k`.** The FDM plan is
     shared — each node demodulates all four carriers — so a partial change
     desyncs the array.
   - `window_n` can only be *lowered* in NVS (the sample buffer is statically
     sized to 1800). Raising it for narrower bins / more processing gain needs a
     firmware rebuild (`WINDOW_N_DEFAULT` in `src/config.h`).

## Flashing

`flash-nvs.sh` expects `nvs/nodeN.csv`, so copy the matching example into place
(and fill in real WiFi/OSC values) before flashing each node:

```sh
cd edge-node
cp nvs/node0.carrier.csv.example nvs/node0.csv   # repeat for 1,2,3
# edit wifi_ssid / wifi_pass / osc_host in each
../scripts/flash-nvs.sh 0 /dev/ttyUSB0           # repeat for 1,2,3
```

Reboot each node after flashing; `f_exc` is recomputed from the new bins at startup.
