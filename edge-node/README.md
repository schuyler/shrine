# MiniCAT Edge Node Firmware

Four ESP32-WROOM-32 nodes performing AC capacitive sensing and cross-node
galvanic skin response (GSR) measurement via frequency-division multiplexing
(FDM). Each node demodulates internal ADC DMA samples in-phase/quadrature and
sends results as OSC packets over WiFi to a SuperCollider host.

## Hardware

### Target board

`esp32dev` (ESP32-WROOM-32, 4 MB flash)

### Pin assignments

| GPIO | Function | Notes |
|------|----------|-------|
| 4 | Excitation output (LEDC) | 50% duty; exact frequency set at startup calibration |
| 36 | ADC input (ADC1_CH0) | Internal ADC, DMA continuous mode, 12-bit |

### ADC

Internal ESP32 ADC1_CH0 (GPIO36) via `adc_continuous` DMA driver. Configured
for `ADC_DIGI_OUTPUT_FORMAT_TYPE1` (2 bytes per sample: bits [11:0] = 12-bit
data, bits [15:12] = channel). Sample rate requested: 220 ksps; actual ~180
ksps due to ESP32 I2S 9/11 clock ratio. Frame size: 2048 bytes (1024 samples).

### Excitation

LEDC high-speed mode (timer 0, channel 0, GPIO 4). Frequency is computed at
startup from the calibrated ADC sample rate and this node's carrier bin:
`f_exc = k_self * fs / N`. All four nodes run simultaneously on distinct
frequencies; no synchronization bus is required.

## Build

Install [PlatformIO](https://platformio.org/), then from `shrine/edge-node/`:

```sh
pio run
```

To build and flash (run on corazon, not the dev machine):

```sh
pio run --target upload
```

Monitor serial output:

```sh
pio device monitor
```

## NVS Provisioning

Each node requires a separate NVS partition containing WiFi credentials and
node parameters. CSV templates are in `nvs/`.

### CSV keys (`shrine` namespace)

| Key | Type | Required | Description |
|-----|------|----------|-------------|
| `node_id` | u8 | yes | Node index, 0–3 |
| `wifi_ssid` | string | yes | WiFi network name (max 32 chars) |
| `wifi_pass` | string | yes | WiFi password (max 64 chars) |
| `osc_host` | string | yes | OSC destination IP, dotted-quad (e.g. `192.168.4.255`) |
| `osc_port` | u16 | yes | OSC destination UDP port. Canonical: `9001` — the conductor's `--listen-port`, which relays the stream on to Pd |
| `base_k` | u16 | no | DFT bin for node 0 (default 180) |
| `step_k` | u16 | no | Bin spacing between nodes (default 20) |
| `window_n` | u16 | no | Samples per demod window (default 1800) |
| `floor_stdev` | u16 | no | Calibration floor for stdev channel (default 0) |
| `floor_gsr0` | u16 | no | Calibration floor for GSR channel 0 (default 0) |
| `floor_gsr1` | u16 | no | Calibration floor for GSR channel 1 (default 0) |
| `floor_gsr2` | u16 | no | Calibration floor for GSR channel 2 (default 0) |
| `ceil_stdev` | u16 | no | Calibration ceiling for stdev channel (default 65535 = unconfigured) |
| `ceil_gsr0` | u16 | no | Calibration ceiling for GSR channel 0 (default 65535 = unconfigured) |
| `ceil_gsr1` | u16 | no | Calibration ceiling for GSR channel 1 (default 65535 = unconfigured) |
| `ceil_gsr2` | u16 | no | Calibration ceiling for GSR channel 2 (default 65535 = unconfigured) |

#### Calibration

Normalized output per channel is computed as:

```
out = clamp((raw - floor) / (ceiling - floor), 0, 1)
```

A channel is unconfigured if any of the following are true: its ceiling key is
absent from NVS, its ceiling value equals 65535 (the sentinel default), or its
ceiling value is less than or equal to its floor. Unconfigured channels output
0.0.

To calibrate a channel: observe the raw signal range under expected operating
conditions, then set `floor_*` to the quiescent (no-touch) value and `ceil_*`
to the maximum expected value. Floor and ceiling are u16 integers matching the
units of the raw signal (stdev or I/Q magnitude × window_n).

### Generate and flash

Requires ESP-IDF on `$IDF_PATH`. Repeat for each node, substituting the CSV
and binary filename. Alternatively, use `scripts/flash-nvs.sh <node_id>`.

```sh
# Generate binary from CSV
python $IDF_PATH/components/nvs_flash/nvs_partition_gen/nvs_partition_gen.py \
    generate nvs/node0.csv nvs/node0.bin 0x6000

# Flash to device (NVS partition offset per partitions.csv)
esptool.py write_flash 0x9000 nvs/node0.bin
```

The NVS partition is at `0x9000`, size `0x6000` (defined in `partitions.csv`).

### Configuration

To change the WiFi network or OSC destination, edit the appropriate fields in
`nvs/nodeN.csv`, then regenerate and reflash the NVS partition. Firmware does
not need to be rebuilt.

To use broadcast delivery, set `osc_host` to the subnet broadcast address
(e.g. `192.168.4.255`). `SO_BROADCAST` is always set on the UDP socket. Prefer
the subnet-directed form over limited broadcast (`255.255.255.255`), which Wi-Fi
APs are more likely to drop or rate-limit (and which fills the 16-byte buffer
exactly).

Send to the **conductor's** port (`9001`, its `--listen-port`), not Pd's. The
conductor binds that port once and relays `/shrine/node/*` on to Pd, so the
sensor stream and the conductor's `/shrine/cue/*` reach Pd off its single bind.
Any number of Python consumers can also bind `9001` (the server sets
`SO_REUSEPORT`) and each receives its own copy of the broadcast. Do not point
the nodes at `9000` — that is the conductor→LED-controller control port, and
mixing the broadcast in there would disrupt that unicast stream.

## Architecture

### Source files

| File | Description |
|------|-------------|
| `src/main.c` | Entry point; NVS init, driver init, task creation |
| `src/config.h` | Pin assignments, ADC/FDM constants, `node_config_t`, `scan_result_t` |
| `src/excitation.c/.h` | LEDC driver; `excitation_init()`, `excitation_start(freq)` |
| `src/adc_read.c/.h` | ADC continuous mode (DMA); `adc_init()`, `adc_calibrate_fs()`, `adc_read_frame()` |
| `src/adc_parse.c/.h` | Pure-C DMA frame parsing (`adc_parse_frame()`) and window accumulation (`window_accumulate()`) |
| `src/fdm_math.c/.h` | NCO-based I/Q demodulation (`fdm_demod_magnitude()`), stdev (`fdm_stdev()`), GSR ordering (`fdm_gsr_ordering()`) |
| `src/sensing_task.c/.h` | FreeRTOS task: calibrate, start excitation, run demod loop |
| `src/network_task.c/.h` | FreeRTOS task: WiFi STA + UDP/OSC transmit |
| `src/nvs_config.c/.h` | NVS read into `node_config_t` |
| `src/globals.h` | `extern QueueHandle_t g_result_queue` |

### Dual-core split

| Core | Task | Priority | Stack |
|------|------|----------|-------|
| Core 1 | `sensing_task` | 20 | 4096 bytes |
| Core 0 | `network_task` | 5 | 8192 bytes |

`sensing_task` owns ADC reads, FDM demodulation, and result production.
`network_task` owns WiFi and UDP/OSC transmission. Results pass between them
via a FreeRTOS queue (depth 4, items of type `scan_result_t`). If the queue is
full when sensing completes a window, the window is dropped silently.

WiFi and lwIP tasks are pinned to Core 0 via `sdkconfig.defaults`
(`CONFIG_ESP_WIFI_TASK_CORE_ID=0`, `CONFIG_LWIP_TASK_CORE_ID=0`), keeping
Core 1 free of network interrupts.

### Data structures

```c
/* node_config_t — loaded from NVS at boot */
typedef struct {
    uint8_t  node_id;
    char     wifi_ssid[33];
    char     wifi_pass[65];
    char     osc_host[16];
    uint16_t osc_port;
    uint16_t base_k;        /* DFT bin for node 0; default 180 */
    uint16_t step_k;        /* bin spacing between nodes; default 20 */
    uint16_t window_n;      /* samples per demod window; default 1800 */
    uint16_t floor_stdev;   /* calibration floor, stdev channel; default 0 */
    uint16_t floor_gsr0;    /* calibration floor, GSR channel 0; default 0 */
    uint16_t floor_gsr1;    /* calibration floor, GSR channel 1; default 0 */
    uint16_t floor_gsr2;    /* calibration floor, GSR channel 2; default 0 */
    uint16_t ceil_stdev;    /* calibration ceiling, stdev channel; default 65535 = unconfigured */
    uint16_t ceil_gsr0;     /* calibration ceiling, GSR channel 0; default 65535 = unconfigured */
    uint16_t ceil_gsr1;     /* calibration ceiling, GSR channel 1; default 65535 = unconfigured */
    uint16_t ceil_gsr2;     /* calibration ceiling, GSR channel 2; default 65535 = unconfigured */
} node_config_t;

/* scan_result_t — produced by sensing_task, consumed by network_task */
typedef struct {
    float   self_stdev;       /* stdev of DC-removed window (self-presence metric) */
    float   self_carrier_mag; /* I/Q magnitude at this node's own carrier */
    float   gsr_mag[3];       /* I/Q magnitude at the 3 other carriers */
    uint8_t gsr_node[3];      /* node IDs corresponding to gsr_mag[] */
    uint8_t node_id;          /* this node's ID */
} scan_result_t;
```

### Startup sequence

1. `nvs_flash_init()` → `nvs_config_load()` — fatal if NVS is unreadable
2. `excitation_init()` — LEDC timer + channel configured, not yet running
3. `adc_init()` — ADC continuous mode (DMA) started; one frame discarded to
   flush stale DMA data
4. Create `g_result_queue`
5. Start `network_task` on Core 0
6. Start `sensing_task` on Core 1

In `sensing_task` startup (before the main loop):

- `adc_calibrate_fs()` — flush 5 stale frames, then time 200 DMA reads to
  measure actual sample rate
- Compute carrier bin `k_self = base_k + node_id * step_k` and excitation
  frequency `f_exc = k_self * fs / N`
- `excitation_start(f_exc)` — begin LEDC output
- Precompute NCO step phasors for all 4 carrier bins

### Sensing loop

Each iteration of the `while(1)` loop in `sensing_task`:

1. `adc_read_frame()` — block on DMA for one 2048-byte frame (~1024 samples)
2. `adc_parse_frame()` — extract 12-bit samples from TYPE1 DMA bytes
3. `window_accumulate()` — append samples to the rolling window buffer;
   returns 1 when the window fills and copies it to a snapshot buffer

   Carry-over: `window_accumulate` tracks position across calls, so samples
   from a frame that spans a window boundary are correctly split between the
   current and next window. The `_Static_assert` in `sensing_task.c` ensures
   one DMA frame cannot fill more than one window, preventing snapshot
   overwrites.

4. When `window_accumulate` returns 1 (window complete):
   - `fdm_stdev()` — stdev of the snapshot (self-presence)
   - `fdm_demod_magnitude()` × 4 — I/Q magnitude at each of the 4 carrier bins
   - Populate `scan_result_t` and post to `g_result_queue`

### FDM carrier allocation

Node carriers are assigned by NVS-configurable parameters. With defaults
(`base_k=180`, `step_k=20`, `window_n=1800`):

| Node | bin k | Frequency (at ~180 ksps) |
|------|-------|--------------------------|
| 0 | 180 | ~18 kHz |
| 1 | 200 | ~20 kHz |
| 2 | 220 | ~22 kHz |
| 3 | 240 | ~24 kHz |

Each node excites at its own frequency and demodulates all four bins from its
ADC input. The three non-self bins measure cross-node (GSR) coupling.

### I/Q demodulation

`fdm_demod_magnitude` in `fdm_math.c` uses an incremental NCO rotation with
internal DC removal (mean subtraction before accumulation) and renormalization
every 64 samples to prevent floating-point drift:

```c
// cos_step = cos(2*PI*k/N),  sin_step = -sin(2*PI*k/N)
float I = 0, Q = 0;
float cos_n = 1.0f, sin_n = 0.0f;
float mean = /* computed over samples */;
for (int i = 0; i < n_samples; i++) {
    float s = (float)samples[i] - mean;
    I += s * cos_n;
    Q += s * sin_n;
    // rotate NCO; renorm every 64 samples
}
return sqrtf(I*I + Q*Q) / n_samples;
```

## OSC Output

Each node sends one UDP/OSC packet per completed window.

| Field | Value |
|-------|-------|
| Address | `/shrine/node/N` (N = node_id, 0–3) |
| Type tag | `fffff` |
| Float 0 | `self_stdev` — stdev of DC-removed window |
| Float 1 | `self_carrier_mag` — I/Q magnitude at this node's own carrier |
| Float 2 | `gsr_mag[0]` — I/Q magnitude at next node's carrier |
| Float 3 | `gsr_mag[1]` — I/Q magnitude at node+2's carrier |
| Float 4 | `gsr_mag[2]` — I/Q magnitude at node+3's carrier |

When calibration is enabled (the compiled default), Floats 0 and 2–4 are
normalized to 0.0–1.0 by the calibration formula. Float 1 (`self_carrier_mag`)
is always the raw I/Q magnitude. When a channel is unconfigured, its normalized
value is 0.0.

`gsr_mag` indices use the `(node_id + offset) % NUM_NODES` convention
(`offset` = 1, 2, 3). The receiver can reconstruct which physical node pair
each index represents from this convention and the known node count (4).

## Build Configuration

### `platformio.ini`

```ini
[env:edge-node]
platform = espressif32@6.9.0
board = esp32dev
framework = espidf
board_build.partitions = partitions.csv
board_build.flash_mode = dio
board_build.flash_size = 4MB
monitor_speed = 115200
build_flags = -DCORE_DEBUG_LEVEL=3
```

### `sdkconfig.defaults`

```
CONFIG_ESP_WIFI_TASK_CORE_ID=0
CONFIG_LWIP_TASK_CORE_ID=0
CONFIG_BT_ENABLED=n
CONFIG_FREERTOS_HZ=1000
CONFIG_ESP_CONSOLE_UART_DEFAULT=y
```

Bluetooth is disabled to reduce memory pressure. `FREERTOS_HZ=1000` gives 1 ms
tick resolution for FreeRTOS delays and timeouts.

## Error Handling

| Condition | Behavior |
|-----------|----------|
| NVS read failure | `ESP_LOGE` + `esp_restart()` |
| ADC calibration failure | `ESP_LOGE` + `esp_restart()` |
| WiFi disconnect | Exponential backoff reconnect, 1 s initial, 30 s maximum |
| ADC read timeout | `ESP_LOGE`; loop continues on next iteration |
| Result queue full | Window dropped silently; no backpressure on sensing |
| UDP send failure | Logged at debug level; loop continues |
