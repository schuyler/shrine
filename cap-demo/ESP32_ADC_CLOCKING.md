# ESP32 ADC Continuous Mode Clocking

Notes on how the ESP32's `adc_continuous` driver (ESP-IDF 5.3.1) determines
the actual ADC sample rate from the requested `sample_freq_hz`.

## Hardware

Target: ESP32-WROOM-32 (ESP32-D0WDQ6, 40 MHz crystal).

## Source files

All paths relative to the PlatformIO framework package
(`~/.platformio/packages/framework-espidf/`).

- `components/esp_adc/adc_continuous.c` — driver entry point
- `components/hal/adc_hal.c` — HAL, including ESP32-specific I2S setup
- `components/hal/esp32/include/hal/adc_ll.h` — low-level register access
- `components/hal/esp32/include/hal/i2s_ll.h` — I2S low-level register access
- `components/hal/i2s_hal.c` — I2S HAL (mclk fractional divider)
- `components/hal/hal_utils.c` — `hal_utils_calc_clk_div_frac_accurate()`

## Clock chain

On ESP32, the `adc_continuous` driver uses I2S0 as a DMA engine for the SAR
ADC.  There are two independent clock domains involved:

### 1. I2S clock (DMA transfer rate)

```
PLL_D2_CLK (160 MHz)
  → fractional mclk divider (clkm_div_num + clkm_div_b/clkm_div_a)
  → mclk
  → ÷ bclk_div (fixed at 16)
  → bclk
```

The driver computes mclk from the requested sample rate:

```c
// adc_hal.c, adc_hal_digi_sample_freq_config(), ESP32 path
uint32_t bclk_div = 16;
uint32_t bclk = sample_freq_hz * 2;
uint32_t mclk = bclk * bclk_div;       // = sample_freq_hz * 32
i2s_hal_calc_mclk_precise_division(160_000_000, mclk, &mclk_div);
i2s_ll_rx_set_mclk(dev, &mclk_div);
i2s_ll_rx_set_bck_div_num(dev, bclk_div);
```

The fractional divider (`hal_utils_calc_clk_div_frac_accurate`) is very
precise — it searches for the closest a/b approximation. For sample rates
whose mclk is an exact divisor of 160 MHz (or close), the I2S clock is
accurate.

The I2S is configured for 16-bit mono ADC mode:

```c
// adc_hal.c, adc_hal_digi_init()
i2s_ll_rx_set_sample_bit(dev, 16, 16);
i2s_ll_rx_enable_mono_mode(dev, 1);     // rx_fifo_mod = 1
i2s_ll_rx_set_ws_width(dev, 16);
i2s_ll_enable_builtin_adc_dac(dev, 1);  // route ADC→I2S
```

### 2. SAR ADC clock (conversion rate)

```
APB_CLK (80 MHz)
  → ÷ sar_clk_div (fixed at 16)
  → SAR_CLK = 5 MHz
```

Set in `adc_hal_digi_init()`:

```c
adc_ll_digi_set_clk_div(ADC_LL_DIGI_SAR_CLK_DIV_DEFAULT);  // = 16
```

The comment in `adc_ll.h` confirms: "ADC clock divided from APB clk, e.g.
80 / 2 = 40Mhz".

### SAR ADC FSM timing (per conversion)

Also set in `adc_hal_digi_init()`:

```c
adc_ll_digi_set_fsm_time(
    ADC_LL_FSM_RSTB_WAIT_DEFAULT,     // 8
    ADC_LL_FSM_START_WAIT_DEFAULT,     // 16 (= SAR_CLK_DIV_DEFAULT)
    ADC_LL_FSM_STANDBY_WAIT_DEFAULT    // 100
);
adc_ll_set_sample_cycle(ADC_LL_SAMPLE_CYCLE_DEFAULT);  // 2
```

Each SAR conversion requires multiple phases.  The per-conversion cycle
count (excluding standby, which may not apply in continuous mode) is:

| Phase        | Cycles |
|--------------|--------|
| rstb_wait    | 8      |
| start_wait   | 16     |
| sample_cycle | 2      |
| conversion   | 12     |
| **Total**    | **38** |

Whether these cycle counts are in SAR_CLK cycles (5 MHz), mclk cycles, or
APB cycles is **not documented in the source**.

## What is NOT clear

The ESP32 path in `adc_hal_digi_sample_freq_config()` configures the I2S
mclk and bclk, but does NOT call `adc_ll_digi_set_trigger_interval()` (which
is used by non-ESP32 targets to set the conversion interval explicitly).

The driver code **assumes** `actual_fs = sample_freq_hz`.  This is wrong.
The measured rate is consistently ~84.9% of the requested rate.

The relationship between the I2S clock configuration and the actual ADC
conversion trigger rate is undocumented in the source.  Two hypotheses:

1. The I2S bclk triggers conversions, but each conversion also requires
   SAR_CLK cycles.  The two clock domains interact to produce the effective
   rate.

2. The SAR ADC controller ignores the I2S timing entirely and converts at
   its own rate (determined by SAR_CLK and FSM timing).  The I2S merely
   provides DMA transport.

Hypothesis 2 is ruled out by empirical data: the actual rate scales
proportionally with the requested rate, so the I2S config does influence the
conversion rate.

## Empirical data

| Requested (Hz) | mclk (Hz)   | mclk_div | Measured (Hz) | Ratio  |
|-----------------|-------------|----------|---------------|--------|
| 150,000         | 4,800,000   | 100/3    | 127,277       | 0.8485 |
| 125,000         | 4,000,000   | 40       | 106,142       | 0.8491 |

The ratio is consistent at **~0.849**.

Equivalently: each sample takes ~37.7 mclk cycles, close to the 38-cycle
FSM total (8 + 16 + 2 + 12).  This suggests the FSM timing may be counted
in mclk cycles, not SAR_CLK cycles, when the ADC is in I2S DMA mode.

## Implications for I/Q demodulation

The I/Q demodulator needs exactly N samples per excitation cycle (currently
N=5).  This requires:

```
actual_fs / excite_freq = 5  (exactly)
```

Since actual_fs ≠ sample_freq_hz, setting excite_freq = sample_freq_hz / 5
does not work.  The phases drift and the demodulator produces random output.

## Approach: derive both rates from the same clock

If both the ADC sample rate and the LEDC excitation frequency divide
cleanly from the same base clock, they will maintain an exact integer
ratio.

**ADC side**: actual_fs = f(mclk) where mclk = 160 MHz / mclk_div.

**LEDC side**: excite_freq = APB / (timer_div × 2^duty_bits).  For a 50%
duty square wave, 1-bit resolution suffices: excite = 80 MHz / (2 × N) =
40 MHz / N.

Since APB = 80 MHz = PLL_D2 / 2 = 160 MHz / 2, and both I2S and LEDC
derive from the same PLL, choosing rates that divide cleanly from 160 MHz
should work.

The missing piece is the exact function f() that converts mclk to actual_fs.
The empirical data suggests f(mclk) ≈ mclk / 37.7, but we need more data
points (or a TRM reference) to nail down the exact formula.

## Recommended next steps

1. **Sweep test**: modify the gsr-rx firmware to try multiple
   `sample_freq_hz` values at startup and log (requested, measured) pairs.
   This will reveal whether the ratio is truly constant, or whether it
   varies with the mclk divider.

2. **Check the TRM**: the ESP32 Technical Reference Manual, Chapter 29
   (SAR ADC) may document the relationship between I2S clocking and SAR
   conversion timing in DMA mode.  The source code does not.

3. **Once f() is known**: choose mclk_div such that f(160M / mclk_div) is
   divisible by 5 and by a convenient excitation frequency.  Set
   sample_freq_hz = (160M / mclk_div) / 32 and excite_freq = f(mclk) / 5.
