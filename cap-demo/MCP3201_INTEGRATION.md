# MCP3201 Integration for Phase-Sensitive GSR

## Goal

Add MCP3201 SPI ADC support to the cap-demo firmware on the RX node so that
cross-body GSR phase can be measured. The ESP32 internal ADC has ~6°/s phase
drift (two separate crystals, no shared clock domain) that makes phase
measurement impossible. The MCP3201 path eliminates this because both LEDC
excitation and SPI sampling derive from the same ESP32 APB clock (80 MHz).

## Background

The bench session on 2026-05-31 validated that:

- Cross-body AC detection works (magnitude ~250 vs baseline ~3-5 at 10× gain)
- Phase is incoherent on the internal ADC at any gain level
- The MCP3201 is the designed path to phase fidelity

See these wiki pages for context:

- **GSR_Skin_Contact_Test** — Bench results from 2026-05-31 session
- **Sensor_Circuit_Design** (section: "ADC — MCP3201") — Wiring and differential input config
- **Sensor_Circuit_Design** (section: "ESP32-WROOM-32 Pin Assignments > SPI Configuration") — GPIO 18/19/21, SPI2_HOST, 1.0 MHz
- **Edge_Node_Firmware** (section: "I/Q Demodulation") — 5-sample tables, calibration strategy
- **Edge_Node_Firmware** (section: "SPI throughput and sample budget") — ~19 µs/sample, ~40 samples in 750 µs
- **Edge_Node_Firmware** (section: "I/Q coherence") — Calibrate sample rate at boot, set LEDC = measured_rate / 5
- **ESP32_ADC_Continuous_Clocking** — Documents why the internal ADC drifts (fractional divider)

## Hardware (Schuyler is wiring this)

MCP3201 (DIP-8) on the RX breadboard:

| MCP3201 pin | Function | Connects to |
|-------------|----------|-------------|
| 1 (Vref)    | Reference voltage | 3.3V |
| 2 (IN+)     | Analog input | TLV2372 pin 7 (Ch B output) |
| 3 (IN−)     | Differential reference | V_mid (1.65V from divider) |
| 4 (Vss)     | Ground | GND |
| 5 (CS)      | Chip select (active low) | ESP32 GPIO 21 |
| 6 (Dout)    | Data output | ESP32 GPIO 19 |
| 7 (CLK)     | SPI clock | ESP32 GPIO 18 |
| 8 (Vdd)     | Power | 3.3V + 100 nF bypass cap |

## Firmware plan

Add a new PlatformIO environment `gsr-rx-spi` with defines
`-DGSR_RX_MODE -DMCP3201_ADC`. The code path in main.c:

### 1. SPI init

- `SPI2_HOST` (HSPI), 1.0 MHz clock
- GPIO 18 = CLK, GPIO 19 = MISO, GPIO 21 = CS
- `mosi_io_num = -1` (read-only device)
- Use `spi_device_acquire_bus()` for fast polling reads

### 2. MCP3201 read function

Single conversion = one 16-bit SPI transaction. Extract 12-bit result:

```c
uint16_t mcp3201_read(spi_device_handle_t dev) {
    spi_transaction_t t = { .length = 16, .rxlength = 16, .flags = SPI_TRANS_USE_RXDATA };
    spi_device_polling_transmit(dev, &t);
    uint16_t raw = (t.rx_data[0] << 8) | t.rx_data[1];
    return (raw >> 2) & 0x0FFF;  // 1 HiZ + 1 null + 12 data + 2 sub-LSB
}
```

### 3. Sample rate calibration (runs once at boot)

Time N back-to-back reads using the same code path as the integration loop.
Compute actual samples per second. Then set LEDC frequency = measured_rate / 5.
This guarantees exactly 5 samples per excitation cycle.

```c
int64_t t0 = esp_timer_get_time();
for (int i = 0; i < CAL_SAMPLES; i++)
    cal_buf[i] = mcp3201_read(dev);
int64_t elapsed = esp_timer_get_time() - t0;
float actual_rate = (float)CAL_SAMPLES / ((float)elapsed / 1e6f);
uint32_t excite_freq = (uint32_t)(actual_rate / 5.0f + 0.5f);
```

### 4. LEDC init at calibrated frequency

Same as the TX node LEDC init but at the calibrated frequency (likely ~10-12 kHz
depending on measured SPI throughput). 1-bit resolution, 50% duty, GPIO 4.

Note: the RX node DOES run excitation in this mode — both nodes excite. The
excitation frequency is set to match the SPI sample rate so the I/Q tables are
correct. The TX node continues running at 20 kHz. The RX node's excitation at
~10-12 kHz is what it demodulates against.

**Wait — this needs reconsideration.** The RX node's excitation must match the
TX node's frequency (20 kHz), not its own sample rate. The I/Q coherence trick
(LEDC = sample_rate / N) only works when the node is demodulating its own
excitation. For cross-node GSR, the RX demodulates the TX's 20 kHz.

### Revised approach: fixed 20 kHz, fractional-sample I/Q

The RX must demodulate at 20 kHz (the TX's frequency). At ~52 ksps (1 MHz SPI),
samples_per_cycle = 52000/20000 = 2.6 — not an integer. Options:

**Option A: Increase SPI clock.** At 1.6 MHz → ~84 ksps → 4.2 samples/cycle.
Still not integer.

**Option B: Set SPI clock so sample rate is an exact multiple of 20 kHz.**
Need sample_rate = N × 20000. At N=5: 100 ksps → SPI clock = 100000 × 16 bits × overhead... The MCP3201 needs 16 clock cycles per conversion plus CS overhead.
At 1.6 MHz SPI clock: ~84 ksps. Can't reach 100 ksps at 3.3V.
At N=4: 80 ksps → need SPI clock ≈ 80000 × ~19µs... that's ~1.5 MHz. Tight but possible.
At N=3: 60 ksps → need ~1.1 MHz SPI. Comfortable.

**Option C: Use the LEDC = sample_rate / N approach but set TX to match.**
Both TX and RX set their LEDC to the calibrated frequency. Flash the TX with the
same `gsr-rx-spi` environment's calibrated rate. Since both derive from 80 MHz
APB, their frequencies will be identical (same divider chain).

**Recommended: Option C.** Both nodes use `gsr-rx-spi` firmware. Each calibrates
its own SPI rate at boot, sets LEDC = rate / 5. Since both ESP32s derive from the
same APB frequency (80 MHz), the LEDC frequencies will be identical across nodes
(same divider → same output frequency). No inter-node crystal mismatch affects
this because LEDC frequency is set by integer divisors of 80 MHz, and both nodes
compute the same divisor from the same SPI timing.

This means: **flash both TX and RX with `gsr-rx-spi` firmware.** The TX runs
excitation but doesn't read the ADC for cross-node purposes (it can still do
self-cap via stdev). The RX reads the MCP3201 and demodulates.

Actually simpler: just flash the TX with the regular `esp32dev` environment but
change EXCITE_FREQ_HZ to match whatever the SPI calibration produces. Or better:
add a calibration step to the TX firmware too.

**Simplest for bench test:** Measure the actual SPI sample rate once, compute
the excitation frequency (rate / 5), hard-code it in both TX and RX firmware,
and test. Parameterize later.

### 5. I/Q demodulation loop

```c
static const float COS_TABLE[5] = {1.0f, 0.3090f, -0.8090f, -0.8090f, 0.3090f};
static const float SIN_TABLE[5] = {0.0f, 0.9511f, 0.5878f, -0.5878f, -0.9511f};

while (1) {
    uint16_t samples[N_SAMPLES];
    for (int i = 0; i < N_SAMPLES; i++)
        samples[i] = mcp3201_read(dev);

    float I = 0, Q = 0;
    double sum = 0, sum_sq = 0;
    for (int i = 0; i < N_SAMPLES; i++) {
        float s = (float)samples[i] - 2048.0f;
        I += s * COS_TABLE[i % 5];
        Q += s * SIN_TABLE[i % 5];
        sum += samples[i];
        sum_sq += (double)samples[i] * samples[i];
    }

    float mag = sqrtf(I*I + Q*Q) / N_SAMPLES;
    float phase = atan2f(Q, I) * 180.0f / M_PI;
    double mean = sum / N_SAMPLES;
    float sd = sqrtf((sum_sq / N_SAMPLES) - mean * mean);

    printf("mag=%.1f phase=%.1f sd=%.0f mean=%.0f n=%d\n",
           mag, phase, sd, mean, N_SAMPLES);
}
```

### 6. Serial output

Same format as current GSR RX mode so plot_iq.py works without modification.

## Implementation steps

1. Add `[env:gsr-rx-spi]` to platformio.ini
2. Add `#ifdef MCP3201_ADC` code path in main.c:
   - SPI init
   - `mcp3201_read()` function
   - Sample rate calibration
   - LEDC init at calibrated frequency
   - I/Q demod loop with 5-sample tables
3. Measure actual SPI sample rate on bench
4. Flash TX node with matching excitation frequency
5. Verify phase stability with a resistor (should be flat, no drift)
6. Test with skin contact — phase should respond to contact quality

## Open question

The "both nodes use calibrated frequency" approach means the excitation frequency
won't be exactly 20 kHz — it'll be whatever rate/5 produces (likely ~10-12 kHz
at 1.0 MHz SPI, or ~16 kHz at 1.6 MHz). This is fine for the measurement
(skin impedance doesn't change dramatically between 10 and 20 kHz), but it
differs from the production design. The production firmware uses the same
calibration trick, so this is consistent.
