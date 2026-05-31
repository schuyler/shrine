# I/Q Demodulation: Current Status and Next Steps

## What we did

Investigated why the ESP32 ADC continuous mode sample rate doesn't match
the requested `sample_freq_hz`, preventing coherent I/Q demodulation.

### Key finding: the 9/11 ratio

The ESP32's `adc_continuous` driver (which uses I2S0 as a DMA engine on
original ESP32) delivers samples at exactly **9/11 of the requested rate**:

```
actual_fs = sample_freq_hz × 9/11
```

This is an undocumented I2S DMA framing property.  We proved:

1. **SAR ADC FSM timing parameters have no effect** — sweeping `rstb_wait`,
   `start_wait`, `sample_cycle`, `sar_clk_div`, and `standby_wait` via
   direct SYSCON register writes produced no measurable change in sample rate.

2. **The ratio is constant across all tested frequencies** (20–200 kHz),
   with `mclk_per_sample` = 352/9 = 39.111 consistently.

3. **This is a known ESP-IDF bug** filed as multiple open issues (IDFGH-15856,
   IDFGH-14457, IDFGH-9225, IDFGH-9195) with no fix from Espressif.

### Phase-locked I/Q demodulation

Since both LEDC and I2S derive from the same 160 MHz PLL, we can choose
parameters where `actual_fs / excite_freq = N` is exact by construction:

```
LEDC (1-bit duty): excite_freq = 80 MHz / (2 × prescaler)
ADC: actual_fs = sample_freq_hz × 9/11
Requirement: prescaler = 440,000,000 × N / (sample_freq_hz × 9)  [integer]
```

Current configuration (N=9):
- `sample_freq_hz` = 220,000
- `actual_fs` = 180,000 Hz
- `excite_freq` = 20,000 Hz (LEDC prescaler = 2000)
- 9 samples per excitation cycle, exact

### Sweep test firmware

A `pio` environment `adc-sweep` is included for diagnostic sweeps.  It can
be re-enabled if needed by building with `-DADC_SWEEP_TEST -DGSR_RX_MODE`.

## What works

- **Magnitude**: stable at ±1% across reads.  No drift, no jumping.
- **Phase within a single DMA read**: stable to ±1° across sub-windows.
- **Phase across reads** (after buffer-overflow fix): stable to ±0.5° per
  read, with a slow drift of ~6°/second.

## What doesn't work

### Phase drift (~6°/second)

After fixing the DMA ring buffer overflow (caused by printf blocking serial
output), phase is stable read-to-read but drifts slowly.  The drift
corresponds to ~0.9 ppm frequency mismatch between the I2S actual sample
rate and exactly 9× the LEDC frequency.

Likely cause: the I2S fractional mclk divider for 160M / 7,040,000 =
22 + 8/11 may not be represented perfectly by the hardware, or there's
a jitter accumulation mechanism in the fractional divider.

### Phase sensitivity at 20 kHz

At 20 kHz, skin capacitive reactance (~265Ω for 30nF) is much smaller than
skin resistance (10kΩ–500kΩ).  Current flows almost entirely through the
capacitive path, making phase nearly insensitive to resistance changes.
The full GSR dynamic range produces only ~3° of phase change at 20 kHz.

For useful phase information, excitation must be at a frequency where ωCR
is in the 0.1–10 range.  The optimal frequency depends on the expected
skin impedance range and is TBD.

## Proposed path forward: MCP3201

An MCP3201 (12-bit SPI ADC) is being added to the board for other reasons
(need ADC1 for cap-touch, ADC2 for WiFi).  It's better suited for
phase-sensitive GSR:

**Advantages:**
- Sample timing is deterministic (SPI clock + hardware timer trigger)
- Trivial integer relationship with LEDC (both divide from 80 MHz APB)
- No DMA buffering mystery — trigger, read, done
- Can use lower excitation frequencies (where phase is sensitive) since
  sample rate is directly controlled
- No 9/11 ratio, no fractional divider drift

**Constraints / unknowns:**
- Max SPI clock: 1.6 MHz at 5V, ~0.8-1.0 MHz at 3.3V.  At 15 clocks per
  conversion, max throughput is ~53-66 ksps at 3.3V, ~106 ksps at 5V.
  ESP32 has a 5V output available.
- What excitation frequency is appropriate?  Need to understand the target
  skin impedance model better.  Traditional EDA uses DC–10 Hz; clinical
  bio-impedance uses 50–100 kHz; the right frequency depends on what
  physiological quantity we're extracting.
- Timer-triggered SPI DMA vs. ISR-driven polling: which gives more
  deterministic timing on ESP32?
- Board layout: which SPI bus, CS pin, proximity to analog front end.

## Architecture summary

| Function | Hardware | Status |
|----------|----------|--------|
| Cap-touch (stdev) | ESP32 ADC1 continuous | Working |
| GSR magnitude | ESP32 ADC1 continuous, 20 kHz | Working (this code) |
| GSR phase | MCP3201 + timer, freq TBD | Not started |
| WiFi | ESP32 (ADC2 stays free) | N/A |

## Files modified

- `cap-demo/src/main.c` — I/Q demod with N=9, phase tracking, sweep test
- `cap-demo/platformio.ini` �� added `adc-sweep` environment
- `cap-demo/ESP32_ADC_CLOCKING.md` — clock chain analysis (pre-existing)
