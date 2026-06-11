# leds

WLED rendering engine (`python -m leds`) and conductor state machine (`python -m leds.conductor`). The rendering engine receives OSC commands and translates them into WLED JSON API calls. The conductor runs a leaky-bucket finite state machine that watches sensor data and drives both the LED engine and the Pd sound engine.

---

## LED controller

```
python -m leds [--config PATH] [--log-level LEVEL]
```

| Argument | Default | Description |
|---|---|---|
| `--config PATH` | `leds/default_config.yaml` | Path to config YAML |
| `--log-level` | `INFO` | `DEBUG` \| `INFO` \| `WARNING` \| `ERROR` |

### Configuration

All keys from `leds/default_config.yaml`:

| Key | Type | Default | Description |
|---|---|---|---|
| `osc_listen_host` | string | `"0.0.0.0"` | OSC listen address |
| `osc_listen_port` | int | `9000` | OSC listen port |
| `wled_targets` | list | — | WLED box list (see below) |
| `wled_port` | int | `80` | WLED HTTP port |
| `wled_timeout` | float | `1.0` | HTTP timeout in seconds |
| `update_rate_hz` | int | `30` | Render loop frequency |
| `pads` | list[int] | `[0, 1, 2, 3]` | Active pad indices |
| `default_program` | string | `"breathe"` | Initial LED program |
| `default_palette` | string | `"default"` | Initial color palette |
| `latency_offset_ms` | float \| `"auto"` | `"auto"` | Beat-phase latency compensation. `"auto"` uses a 10-tap EMA of round-trip time (RTT/2). |

#### `wled_targets`

Each entry maps one WLED box to a pad index:

```yaml
wled_targets:
  - host: "wled-a.local"
    pad: 0
    color: [217, 24, 40]   # optional signature RGB
  - host: "wled-b.local"
    pad: 1
```

Each WLED box must have segments at indices 0 and 1 pre-configured — the controller duplicates output to both. `color` is loaded as `PadSnapshot.signature_color`; programs use it as the base color and fall back to palette `idle` when absent.

At startup the controller fetches the live effect name list from the first target in `wled_targets`. If that fetch fails it falls back to a built-in table. This ensures `/leds/effect` name strings match the running firmware.

---

## Conductor

```
python -m leds.conductor [options]
```

| Argument | Default | Description |
|---|---|---|
| `--conductor-config PATH` | `conductor.yaml` (repo root) | Path to conductor config |
| `--listen-host HOST` | `0.0.0.0` | OSC listen address |
| `--listen-port PORT` | `9001` | OSC port for `/shrine/node/*` messages |
| `--led-host HOST` | `127.0.0.1` | LED controller address |
| `--led-port PORT` | `9000` | LED controller port |
| `--pd-host HOST` | `127.0.0.1` | Pd address |
| `--pd-port PORT` | `57120` | Pd port |
| `--tick-rate HZ` | `30.0` | Conductor tick rate |
| `--log-level` | `INFO` | `DEBUG` \| `INFO` \| `WARNING` \| `ERROR` |

The conductor receives `/shrine/node/<id>` OSC messages (stdev, carrier_mag, gsr0, gsr1, gsr2) from the edge nodes, relays them verbatim to Pd, and feeds them into the leaky-bucket FSM. On state changes it sends `/leds/program`, `/leds/palette`, and `/shrine/cue/state` to the LED stack and Pd respectively. Tempo is broadcast to both at ~1 Hz. Group membership changes are sent to both as `/leds/group` and `/shrine/cue/group`. On each transition to Quiet the conductor picks a fresh major-pentatonic tonic and sends it to Pd as `/shrine/cue/root`.

### `conductor.yaml` reference

All time values are in seconds unless noted.

#### `sensing`

Schmitt trigger thresholds applied to raw sensor values before they enter the FSM. All pad presence and pair-connection decisions go through hysteresis + hold-time debouncing.

| Key | Description |
|---|---|
| `cap_on_threshold` | Cap signal level (0–1) above which a pad is considered touched |
| `cap_off_threshold` | Cap signal level below which a touched pad is released |
| `cap_hold_on` | Seconds the signal must stay above `cap_on_threshold` to confirm engagement |
| `cap_hold_off` | Seconds the signal must stay below `cap_off_threshold` to confirm release |
| `gsr_on_threshold` | GSR magnitude (0–1) above which a pad pair is considered connected |
| `gsr_off_threshold` | GSR magnitude below which a connected pair is disconnected |
| `gsr_hold_on` | Hold time to confirm GSR connection |
| `gsr_hold_off` | Hold time to confirm GSR disconnection |
| `confirm_hold` | Seconds the upward-transition condition must hold continuously before the FSM advances |

#### `buckets`

Leaky-bucket parameters for each accumulating state. The bucket fills while the qualifying condition holds and drains when it lapses; the state advances when the bucket is full AND the condition has been held continuously for `confirm_hold` seconds.

```yaml
buckets:
  seeking:
    fill_rate: 1.0    # seconds of credit per second while ≥1 pad engaged
    drain_rate: 0.5   # seconds drained per second while no pad engaged
    full_at: 120.0    # bucket capacity
    entry_seed: 0.0   # initial fill on state entry

  aligning:
    fill_rate: 1.0    # fills while group ≥ 2
    drain_rate: 0.5
    full_at: 120.0
    entry_seed: 60.0

  energizing:
    fill_rate: 1.0    # fills while group ≥ 3
    drain_rate: 0.5
    full_at: 60.0
    entry_seed: 30.0

  ascending:
    dwell: 60.0       # fixed duration before decaying back to Energizing
```

Ascending has no fill/drain — `dwell` is the unconditional duration before the state decays.

#### `tempo`

BPM per state. A scalar is a fixed BPM; a `[lo, hi]` pair is interpolated linearly by the current bucket fill fraction (0 = empty → lo, 1 = full → hi).

```yaml
tempo:
  quiet: 50
  seeking: [60, 70]
  aligning: [70, 80]
  energizing: [80, 90]
  ascending: 100
```

Tempo is not hot-reloadable; changes require a conductor restart.

#### `subdiv` (optional)

The melodic re-fire grid per state, in clock ticks per re-fire (the Pd clock runs a 16th-note tick, 4 ticks/beat): `16`=bar, `8`=half, `4`=quarter, `2`=eighth, `1`=sixteenth. Smaller = denser. A held connection re-advances the melodic walk on this grid (the first note still fires immediately on touch), so the texture reads as rhythm rather than scattered chimes; the grid tightens as the room comes together. Like `tempo`, a scalar is fixed and a `[calm, agitated]` pair interpolates by bucket fill — in log2 space, snapped to a musical power of two. Values must be in `{1, 2, 4, 8, 16}`.

```yaml
subdiv:
  quiet: 16          # bar
  seeking: [16, 8]   # bar → half
  aligning: [8, 4]   # half → quarter
  energizing: [4, 2] # quarter → eighth
  ascending: 2       # eighth
```

Broadcast on `/shrine/cue/refire` at ~1 Hz. Omit the whole section to disable (the conductor then sends no `refire` cue and the Pd gate uses its default grid). Like `tempo`, not hot-reloadable.

#### `idle`

Global idle timeout. The idle accumulator fills while zero pads are engaged and drains while any pad is engaged. When it reaches `timeout` from any state, the FSM collapses to Quiet.

| Key | Description |
|---|---|
| `timeout` | Seconds of zero engagement before forced Quiet transition |
| `drain_rate` | Rate (seconds per second) at which the accumulator drains while any pad is engaged |

#### `programs` / `palettes`

Maps FSM state names to LED program and palette strings. Every state (`quiet`, `seeking`, `aligning`, `energizing`, `ascending`) must have an entry; missing entries are a fatal startup error.

```yaml
programs:
  quiet: "breathe"
  seeking: "pulse"
  aligning: "converge"
  energizing: "converge"
  ascending: "bloom"

palettes:
  quiet: "default"
  seeking: "default"
  aligning: "default"
  energizing: "default"
  ascending: "ascending"
```

These sections are hot-reloadable. Edit `conductor.yaml` while the conductor is running and the changes take effect within ~0.5 seconds. The current state's program and palette are immediately re-sent to the LED stack. Failed reloads (bad YAML or missing keys) log a warning and leave the previous mappings in place; the next save attempt is not suppressed.

---

## FSM states

```
QUIET → SEEKING → ALIGNING → ENERGIZING → ASCENDING
                ←           ←             ↓
                                      (dwell expires → ENERGIZING)
```

| State | Qualifying condition | Fills when |
|---|---|---|
| QUIET | — | — |
| SEEKING | ≥1 pad engaged + confirm_hold | ≥1 pad engaged |
| ALIGNING | ≥2 pads in group + confirm_hold | group ≥ 2 |
| ENERGIZING | ≥3 pads in group + confirm_hold | group ≥ 3 |
| ASCENDING | — | fixed dwell |

Group membership is the largest connected component of the pad graph, where edges are confirmed GSR connections.

Downward transitions happen when a bucket empties: Aligning → Seeking, Energizing → Aligning. The global idle timeout overrides all of these and forces a direct drop to Quiet.

---

## OSC interface

### LED controller (`/leds/*`, port 9000)

| Path | Args | Description |
|---|---|---|
| `/leds/cap` | `i f` — pad (0-indexed), value (0–1) | Capacitive presence |
| `/leds/heartbeat` | `i f` — pad, Hz | Heartbeat frequency (0 = none) |
| `/leds/flux` | `i f` — pad, value (0–1) | Signal fluctuation |
| `/leds/program` | `s` — name | Switch active program |
| `/leds/palette` | `s` — name | Switch active palette |
| `/leds/tempo` | `f` — BPM | Tempo for beat sync |
| `/leds/effect` | `i s [i i i i]` — pad, effect name or fx ID, optional bri, sx, ix, pal | Force a WLED effect onto a pad. Pass `"off"`, `"clear"`, or `"none"` as the effect to release the override. |
| `/leds/effect/clear` | (none) | Release all effect overrides |
| `/leds/group` | `i...` — variable number of pad IDs | Set pad group topology |

### Conductor → Pd (`/shrine/cue/*`, port 57120)

| Path | Args | Description |
|---|---|---|
| `/shrine/cue/state` | `s` — state name (lowercase) | FSM state transition |
| `/shrine/cue/group` | `i...` — pad IDs | Group membership change |
| `/shrine/cue/tempo` | `f` — BPM | Tempo, sent ~1 Hz |
| `/shrine/cue/refire` | `i` — clock ticks per re-fire | Melodic re-fire grid, sent ~1 Hz (only if `subdiv:` configured) |
| `/shrine/cue/root` | `i` — MIDI note | Melodic tonic, sent on each Quiet transition |

The conductor also relays raw `/shrine/node/<id>` messages to Pd verbatim.

---

## Programs

| Program | Used in | Description |
|---|---|---|
| `breathe` | Quiet | Brightness oscillates with cap presence; uses signature color blended toward palette `warm`. |
| `pulse` | Seeking | Active pads show a slow WLED Comet effect in signature color. Inactive pads show a dim glow. |
| `converge` | Aligning, Energizing | Pads in the group blend their signature colors toward a common centroid. Blend amount scales with group size. |
| `chase` | — | WLED Chase effect; speed is mapped from heartbeat frequency. Falls back to breathe-like rendering when heartbeat is absent. |
| `bloom` | Ascending | All pads lit with the palette `unison` color; brightness pulses once per bar. |
| `dazzle` | — | Signature colors rotate one station per beat on the bar phase. |

---

## Writing a new program

Subclass `Program` from `leds.programs`, implement `name`, `initial_state`, and `render`, then decorate with `@register`:

```python
from leds.programs import Program, SegmentParams, register

@register
class MyProgram(Program):
    @property
    def name(self) -> str:
        return "my-program"

    def initial_state(self) -> dict:
        return {}

    def render(self, pads, palette, clock_phase, state: dict) -> tuple[list[SegmentParams], dict]:
        segments = []
        for pad in pads:
            segments.append(SegmentParams(
                col=[[255, 255, 255]],
                bri=128,
            ))
        return segments, state
```

`render()` parameters:

| Parameter | Type | Description |
|---|---|---|
| `pads` | `list[PadSnapshot]` | One snapshot per active pad. Fields: `cap` (0–1), `heartbeat` (Hz), `flux` (0–1), `signature_color` (RGB list or None), `group` (frozenset of pad IDs). |
| `palette` | `dict` | Active palette. Keys depend on the palette YAML; standard keys are `idle`, `warm`, `unison`. |
| `clock_phase` | `ClockPhase` | `beat` (0–1 within current beat) and `bar` (0–1 within current 4-beat bar). |
| `state` | `dict` | Program's own persistent state, returned from the previous `render()` call. |

Return a list of `SegmentParams` (one per pad, in the same order as `pads`) and the updated state dict.

`SegmentParams` fields:

| Field | Type | Default | Description |
|---|---|---|---|
| `col` | `list[list[int]]` | required | Up to 3 RGB triples |
| `bri` | `int` | required | Brightness 0–255 |
| `fx` | `int \| str` | `0` | WLED effect ID or name |
| `sx` | `int` | `128` | Effect speed parameter |
| `ix` | `int` | `128` | Effect intensity parameter |
| `pal` | `int` | `0` | WLED palette index |
| `on` | `bool` | `True` | Segment on/off |

After implementing, import the module in `leds/programs/__init__.py` to trigger registration:

```python
from leds.programs import my_program as _my_program  # noqa: E402, F401
```

Then reference the name in `conductor.yaml` under `programs:`.

---

## Tests

```bash
uv run pytest leds/tests/
```
