# MiniCAT Edge Node Firmware

Four ESP32-S3 nodes performing AC capacitive sensing and cross-node galvanic
skin response (GSR) measurement. Each node demodulates ADC samples in-phase/
quadrature and sends results as OSC packets over WiFi to a SuperCollider host.

## Hardware

### Target board

`esp32-s3-devkitc-1` (4 MB flash)

### Pin assignments

| GPIO | Function | Notes |
|------|----------|-------|
| 4 | Excitation output (LEDC) | ~20 kHz, 50% duty, exact freq set at startup calibration |
| 5 | Sync bus | Leader: push-pull output. Follower: rising-edge interrupt input. |
| 10 | SPI CS | Software-controlled |
| 12 | SPI CLK | `SPI2_HOST`, 1.0 MHz |
| 13 | SPI MISO | MCP3201 D_out |
| 19, 20 | USB-CDC | Debug log output only |

### ADC

MCP3201 12-bit SPI ADC. MOSI is not connected (`mosi_io_num = -1`). Raw frame
extraction: `(raw >> 2) & 0x0FFF` (1 null bit + 12 data bits MSB-first +
3 sub-LSB echo bits).

### Sync bus

A single wire connects GPIO 5 on all four nodes. One node is designated leader
in NVS (`leader=1`); the other three are followers. The leader drives a ~5 µs
pulse every 10 ms. Followers trigger on the rising edge.

## Build

Install [PlatformIO](https://platformio.org/), then from `shrine/edge-node/`:

```sh
pio run
```

To build and flash:

```sh
pio run --target upload
```

Monitor serial output:

```sh
pio device monitor
```

## NVS Provisioning

Each node requires a separate NVS partition. CSV templates are in `nvs/`.

### CSV keys (`shrine` namespace)

| Key | Type | Description |
|-----|------|-------------|
| `node_id` | u8 | Node index, 0–3 |
| `leader` | u8 | 1 = leader (drives sync pulse), 0 = follower |
| `wifi_ssid` | string | WiFi network name (max 32 chars) |
| `wifi_pass` | string | WiFi password (max 64 chars) |
| `osc_host` | string | OSC destination IP, dotted-quad (e.g. `192.168.4.255`) |
| `osc_port` | u16 | OSC destination UDP port (e.g. `57120`) |

### Generate and flash

Requires ESP-IDF on `$IDF_PATH`. Repeat for each node, substituting the CSV
and binary filename.

```sh
# Generate binary from CSV
python $IDF_PATH/components/nvs_flash/nvs_partition_gen/nvs_partition_gen.py \
    generate nvs/node0.csv nvs/node0.bin 0x6000

# Flash to device (NVS partition offset per partitions.csv)
esptool.py write_flash 0x9000 nvs/node0.bin
```

The NVS partition is at `0x9000`, size `0x6000` (defined in `partitions.csv`).

### Configuration

To change the WiFi network or OSC destination, edit the `wifi_ssid`,
`wifi_pass`, and `osc_host`/`osc_port` fields in the appropriate `nvs/nodeN.csv`
file, then regenerate and reflash the NVS partition. Firmware does not need
to be rebuilt.

To use broadcast delivery, set `osc_host` to the subnet broadcast address
(e.g. `192.168.4.255`). `SO_BROADCAST` is always set on the UDP socket.

## Architecture

### Dual-core split

| Core | Task | Priority | Stack |
|------|------|----------|-------|
| Core 1 | `sensing_task` | 20 | 4096 bytes |
| Core 0 | `network_task` | 5 | 8192 bytes |

`sensing_task` owns excitation gating, SPI ADC reads, and I/Q demodulation.
`network_task` owns WiFi and UDP/OSC transmission. Results pass between them
via a FreeRTOS queue (depth 4, items of type `scan_result_t`). If the queue is
full when sensing completes a frame, the frame is dropped silently.

WiFi and lwIP tasks are pinned to Core 0 via `sdkconfig.defaults`
(`CONFIG_ESP_WIFI_TASK_CORE_ID=0`, `CONFIG_LWIP_TASK_CORE_ID=0`), keeping
Core 1 free of network interrupts.

### Startup sequence

1. `nvs_flash_init()` → `nvs_config_load()` — fatal if NVS is unreadable
2. `excitation_init()` — LEDC timer + channel, stopped
3. `adc_init()` — `SPI2_HOST` bus + MCP3201 device
4. `sync_init(is_leader)` — GPTimer (leader) or GPIO ISR (follower)
5. Create result queue
6. Start `network_task` on Core 0
7. Start `sensing_task` on Core 1

### TDM frame structure

One frame is 10 ms (100 Hz), divided into 10 slots of 1 ms each.

- **Slots 0–3**: self-capacitance. Each node excites and reads its own
  electrode in its assigned slot (node N in slot N).
- **Slots 4–9**: cross-node GSR. One node excites; a different node reads.

Per-slot timing: 250 µs settling, 750 µs integration (~40 ADC samples at
1 MHz SPI clock). The TX node holds excitation on until the full 1 ms slot
elapses, so the RX node sees a stable signal during integration.

GSR slot assignments:

| Slot | TX | RX |
|------|----|----|
| 4 | 0 | 1 |
| 5 | 0 | 2 |
| 6 | 0 | 3 |
| 7 | 1 | 2 |
| 8 | 1 | 3 |
| 9 | 2 | 3 |

Node 0 is never a GSR receiver; node 3 is a receiver in three slots. Each
node populates only the `gsr_mag`/`gsr_phase` indices corresponding to its
RX slots; unused indices remain 0.0.

### Sync mechanism

Leader: GPTimer alarm at 1 µs resolution fires every 10 ms. The IRAM ISR
pulses GPIO 5 high for ~5 µs, then gives `g_sync_sem`. Follower: GPIO 5
rising-edge ISR gives `g_sync_sem`. Both roles use the same sensing loop:
`xSemaphoreTake(g_sync_sem, 15 ms timeout)`. Follower blocks with no output
if no pulse arrives within the timeout and recovers automatically on the next
pulse.

### Sample rate calibration

At startup, `sensing_task` times 500 back-to-back MCP3201 reads using the
same `adc_read_into_buffer()` call path used during integration. The measured
sample rate is divided by `SAMPLES_PER_CYCLE` (5) to derive the LEDC
excitation frequency, guaranteeing an integer number of ADC samples per
excitation cycle. The calibration result is logged at boot.

### I/Q demodulation

```c
static const float COS_TABLE[5] = { 1.0f,  0.3090f, -0.8090f, -0.8090f,  0.3090f };
static const float SIN_TABLE[5] = { 0.0f,  0.9511f,  0.5878f, -0.5878f, -0.9511f };

float I = 0, Q = 0;
for (int i = 0; i < n_samples; i++) {
    float s = (float)samples[i] - 2048.0f;  // remove 12-bit midpoint DC
    I += s * COS_TABLE[i % 5];
    Q += s * SIN_TABLE[i % 5];
}
float magnitude = sqrtf(I*I + Q*Q) / n_samples;
float phase     = atan2f(Q, I);
```

## OSC Output

Each node sends one UDP/OSC packet per frame (100 Hz).

| Field | Value |
|-------|-------|
| Address | `/shrine/node/N` (N = node_id, 0–3) |
| Type tag | `fffffff` |
| Float 0 | `self_cap_mag` |
| Float 1 | `gsr_mag[0]` |
| Float 2 | `gsr_mag[1]` |
| Float 3 | `gsr_mag[2]` |
| Float 4 | `gsr_phase[0]` |
| Float 5 | `gsr_phase[1]` |
| Float 6 | `gsr_phase[2]` |

`gsr_mag` and `gsr_phase` indices map to the node's RX slots in ascending slot
order. Unused positions (node 0 has no GSR RX slots; node 1 has one) are 0.0.
On SPI error the affected slot's values are `NaN`.

The receiver must consult the static GSR schedule to interpret which
cross-node pair each `gsr_*` index represents.

## Error Handling

| Condition | Behavior |
|-----------|----------|
| NVS read failure | `ESP_LOGE` + `esp_restart()` |
| WiFi disconnect | Exponential backoff reconnect, 1 s initial, 30 s maximum |
| Sync loss (follower) | Semaphore timeout after 15 ms; no output until next pulse |
| SPI error | Affected slot values set to `NaN`; loop continues |
| Result queue full | Frame dropped silently; no backpressure on sensing |
| UDP send failure | Logged at debug level; loop continues |
