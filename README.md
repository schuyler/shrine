# Shrine

Interactive sound-and-light installation driven by capacitive and galvanic skin
response sensors. Four ESP32 sensor nodes detect touch and inter-person contact,
feeding a state machine that drives a Pure Data sound engine and WLED LED
controllers.

## Architecture

```
  ┌─────────────────────────────────────────────────────┐
  │  4x ESP32 edge nodes                                 │
  │  AC capacitive + FDM cross-node GSR sensing          │
  │  /shrine/node/{0-3} fffff   →   broadcast UDP :9001 │
  └────────────────────────┬────────────────────────────┘
                           │ UDP/OSC :9001
                           ▼
  ┌────────────────────────────────────────────────────┐
  │  Conductor  (python -m leds.conductor)             │
  │  FSM: quiet → seeking → aligning → energizing      │
  │              → ascending                           │
  │                                                    │
  │  relays /shrine/node/*  ──────────────────────┐   │
  │  sends  /shrine/cue/*   ──────────────────────┤   │
  │  sends  /leds/*         ───────┐              │   │
  └────────────────────────────────┼──────────────┼───┘
                                   │              │
                     UDP/OSC :9000 │              │ UDP/OSC :57120
                                   ▼              ▼
  ┌──────────────────────────┐   ┌───────────────────────────┐
  │  LED controller          │   │  Pd  (pd/main.pd)         │
  │  (python -m leds)        │   │  additive drones +        │
  │  programs, palettes,     │   │  SoundFont melodic layer  │
  │  beat sync               │   │  4-channel audio out      │
  └──────────────┬───────────┘   └───────────────────────────┘
                 │ HTTP JSON
                 ▼
  ┌─────────────────────────┐
  │  WLED boxes (4x)        │
  │  one per pad station    │
  └─────────────────────────┘
```

### Port map

| Port  | Protocol | Bound by        | Traffic                              |
|-------|----------|-----------------|--------------------------------------|
| 9001  | UDP/OSC  | Conductor       | `/shrine/node/*` from edge nodes     |
| 57120 | UDP/OSC  | Pd              | `/shrine/node/*` + `/shrine/cue/*` from conductor |
| 9000  | UDP/OSC  | LED controller  | `/leds/*` from conductor             |
| 80    | HTTP     | WLED boxes      | JSON segment API from LED controller |

Pd binds 57120 once; the conductor relays both the node stream and its own
cue events to that single port. Do not point edge nodes at 57120 or 9000 —
only at 9001.

## Prerequisites

- Python 3.11+ and [uv](https://docs.astral.sh/uv/)
- [PlatformIO](https://platformio.org/) (firmware builds only)
- Pure Data 0.56+ with the [ELSE library](https://github.com/porres/pd-else) (required for `[sfont~]`)
- WLED 16.x on the LED controller ESP32s

## Quick start

Dev setup — runs the full stack on one machine with simulated sensor data:

```bash
uv sync
uv run python osc-sim/generator.py --host localhost   # automated sensor scenario
uv run python -m leds.conductor                        # state machine (binds :9001)
uv run python -m leds                                  # LED renderer (binds :9000)
pd -path pd pd/main.pd                                 # sound engine (binds :57120)
```

For hands-on control of sensor state, use `manual.py` instead of `generator.py`:

```bash
uv run python osc-sim/manual.py --host localhost
```

Production setup (on the target host):

```bash
sudo scripts/setup-audio.sh    # install packages, configure RT audio, install systemd units
scripts/deploy.sh              # rsync source from dev machine to corazon:shrine/
```

Firmware is built and flashed on corazon, not from the dev machine:

```bash
cd edge-node && pio run --target upload
```

## Directories

| Path              | Description |
|-------------------|-------------|
| `pd/`             | Pure Data sound engine — drones, melodic voices, mixing |
| `leds/`           | LED rendering engine and conductor state machine |
| `edge-node/`      | ESP32 capacitive/GSR sensor firmware (ESP-IDF) |
| `osc-sim/`        | OSC sensor simulators for development |
| `scripts/`        | Deployment, firmware flashing, diagnostics |
| `systemd/`        | Service units for production host |
| `wled/`           | WLED firmware provisioning and setup |
| `sounds/`         | SoundFont sample library (not tracked in git) |
| `conductor.yaml`  | Conductor state machine config (hot-reloadable) |

## OSC reference

### Sensor data — edge nodes → conductor, port 9001

| Path               | Args    | Description |
|--------------------|---------|-------------|
| `/shrine/node/{0-3}` | `fffff` | `self_stdev`, `carrier_mag`, `gsr_mag[0-2]`, normalized 0–1 |

### Conductor cues — conductor → Pd, port 57120

| Path               | Args     | Description |
|--------------------|----------|-------------|
| `/shrine/node/{0-3}` | `fffff` | Relayed sensor data |
| `/shrine/cue/state`  | `s`     | FSM state: `quiet` / `seeking` / `aligning` / `energizing` / `ascending` |
| `/shrine/cue/group`  | `i...`  | Pad IDs in the largest connected group |
| `/shrine/cue/tempo`  | `f`     | Current tempo in BPM |
| `/shrine/cue/root`   | `i`     | Melodic tonic as MIDI note number |

### LED control — port 9000

Accepted by the LED controller. The conductor sends `/leds/cap`, `/leds/program`,
`/leds/palette`, `/leds/tempo`, and `/leds/group`. The remaining paths are
available for manual control or future use.

| Path                 | Args             | Description |
|----------------------|------------------|-------------|
| `/leds/cap`          | `i f`            | Pad index + capacitive presence 0–1 |
| `/leds/heartbeat`    | `i f`            | Pad index + heartbeat frequency in Hz |
| `/leds/flux`         | `i f`            | Pad index + signal fluctuation 0–1 |
| `/leds/program`      | `s`              | Switch LED program by name |
| `/leds/palette`      | `s`              | Switch color palette by name |
| `/leds/tempo`        | `f`              | Tempo in BPM for beat sync |
| `/leds/effect`       | `i s [i i i i]` | Force WLED effect on pad: index, name/id, optional bri/sx/ix/pal |
| `/leds/effect/clear` | (none)           | Release all effect overrides |
| `/leds/group`        | `i...`           | Connected pad IDs |

## Further reading

- [`edge-node/README.md`](edge-node/README.md) — firmware architecture, NVS provisioning, FDM carrier allocation
- [`osc-sim/README.md`](osc-sim/README.md) — manual and automated simulators
- [`pd/README.md`](pd/README.md) — sound engine patches, OSC contract, testing
- [`leds/README.md`](leds/README.md) — LED controller, conductor, programs
- [`scripts/README.md`](scripts/README.md) — deployment, firmware tools, diagnostics
- [`systemd/README.md`](systemd/README.md) — production services and configuration
- [`wled/README.md`](wled/README.md) — WLED setup and provisioning
