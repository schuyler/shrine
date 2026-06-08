# Shrine Pure Data sound engine

Pure Data audio engine for the **Shrine of Inter-Dimensional Propitiation**. It
receives OSC from the four ESP32 sensor nodes and turns capacitive + GSR sensing
into sound. See the BSS wiki pages `Pd_Architecture`, `Voice_Architecture`,
`Pd_Build_Plan`, and `Sound_Design_Cookbook` for the full design.

The engine is intentionally **two engines split by layer**:

- **Additive drones** — four presence-drones (one per pad), cap-driven amplitude
  and detune. Continuous, per-partial, body-coupled. (`drone.pd`)
- **SoundFont texture voices** — cap-triggered sfont~ voices with threshold-based
  note on/off, intensity from cap presence, heartbeat extraction for rate
  modulation. (`texture-test.pd` + `cap-trigger.pd` + `heartbeat.pd`)

## The OSC contract (real, as wired here)

This is the contract actually emitted by `edge-node` firmware
(`network_task.c`) and `osc-sim/generator.py`, and consumed by `leds/` — **not**
the older contract some wiki pages described. It is the source of truth for this
code.

```
/shrine/node/{0..3}  ->  5 floats (0-1 normalized):
    [0] self_stdev    -> pad presence ("cap"); node N -> bus cap-N
    [1] carrier_mag   -> ignored / dropped
    [2..4] gsr_mag0..2 -> 3 GSR magnitudes, mapped to global pairs by node
```

GSR slot → global pair mapping (`NODE_GSR_MAPPING`, see `leds/sensor_state.py`):

| node | gsr_mag0 | gsr_mag1 | gsr_mag2 |
|------|----------|----------|----------|
| 0    | pair 0   | pair 1   | pair 2   |
| 1    | pair 3   | pair 4   | pair 0   |
| 2    | pair 5   | pair 1   | pair 3   |
| 3    | pair 2   | pair 4   | pair 5   |

Each pair is sensed by two nodes (redundant); last writer wins, as in `leds/`.

**Value ranges:** firmware sends calibrated 0–1 normalized values. The simulator
(`osc-sim/generator.py`) also sends 0–1 directly. `osc-receive.pd` clips to 0–1
but does not rescale.

### Named buses

`osc-receive` publishes these via `[send]`; everything downstream `[receive]`s them:

- `cap-0` … `cap-3` (0–1) — per-pad presence (0-indexed, matches node ID)
- `gsr-mag-0` … `gsr-mag-5` (0–1) — per-pair contact magnitude

There is **no per-pair GSR stdev** in the real data (the wiki's `gsr-std-0..5`
buses were never backed by a signal). The "restlessness" the design needs for
rhythmic subdivision is therefore **derived host-side** in `restless.pd` from the
fluctuation of an existing stream (cap or gsr-mag).

## Files

| File | Status | Purpose |
|------|--------|---------|
| `osc-receive.pd` | **verified** | ELSE osc.receive/osc.route → `cap-*` / `gsr-mag-*` buses |
| `cap-trigger.pd` | **verified** | threshold note on/off from cap presence (`$1`=threshold) |
| `heartbeat.pd` | **stub** | outputs constant 1 (bp~ at 1.2 Hz diverges at 48 kHz; needs control-rate approach) |
| `texture-test.pd` | **wired** | sfont~ texture voices: brent (cap-0) + jeanne (cap-1) |
| `drone.pd` | **verified** | additive presence drone (inlet0 cap, inlet1 base Hz) |
| `master.pd` | verified (load) | per-channel soft-limit → `dac~ 1-4` |
| `clock.pd` | verified (load) | global pulse: `beat`, `bar`, `beat-ms` (default 60 BPM) |
| `mode-table.pd` | **verified** | fills `mode-notes` array (major pentatonic, MIDI 36–93) |
| `restless.pd` | **verified** | fluctuation proxy 0–1 (replaces absent gsr-stdev) |
| `melodic-voice.pd` | **verified** (note-gen) | per-pair walk → MIDI to `[s voice-midi]` |
| `monitor.pd` | verified (load) | DEV-ONLY bus printer (do not load in production) |
| `main.pd` | verified (load) | top level: OSC + 4 drones + master |
| `sfont-host.pd` | **DRAFT** | `[sfont~]` host — needs ELSE + on-target verification |

"verified" = exercised headless under Pd 0.54 with the real OSC format / signal
measurement (see Testing). "verified (load)" = loads clean, components verified
individually. "wired" = connections reviewed but not yet tested on target.

## Running

Target platform is **Pd 0.56+ with the ELSE library** (for `[sfont~]`):
on Debian 13, install Pd from `trixie-backports` and ELSE via Deken (see
`Pd_Build_Plan`). Vanilla parts run on Pd ≥ 0.51.

Dev (GUI, with the simulator):

```bash
pd -path pd pd/main.pd            # open the engine
uv run python osc-sim/generator.py --host localhost   # feed it sensor data
```

Production (headless), per `Pd_Architecture`:

```bash
pd -nogui -rt -audioapi alsa -r 48000 -outchannels 8 \
   -audiooutdev "USB Audio" -path pd pd/main.pd
```

## Testing (headless)

The patches are validated by loading them under `pd -nogui -noaudio -stderr` and
either driving real OSC at them or measuring DSP with `env~`/`snapshot~`, with a
`[delay]→; pd quit` to self-terminate. Example — end-to-end OSC contract check:

```bash
pd -nogui -noaudio -stderr -path pd test/osctest.pd &   # prints each bus
uv run python test/send_nodes.py                        # sends /shrine/node/*
```

## Gotchas discovered (worth knowing before editing)

- **ELSE osc.route vs vanilla oscparse:** `osc-receive.pd` uses ELSE
  `osc.receive` + cascaded `osc.route` (vanilla `oscparse` didn't work).
  ELSE `osc.route` outputs "anything" messages that `unpack` rejects — a
  `list prepend` before `unpack` normalizes the message type. FFT messages
  (`/shrine/node/N/fft`) must be caught by a first-stage `osc.route` or they
  cause type-mismatch errors in `unpack`.
- **Abstraction `$`-args** work in `[send]`/`[receive]` *names* (`r cap-$1`) but
  **not as numeric values** (`[f $1]` yields 0). Pass values via inlets instead —
  that's why `drone` takes its base frequency on an inlet.
- **Commas and semicolons in `#X text` comments** must be escaped (`\,` `\;`) or
  Pd parses the tail as a separate message and throws "no method" errors.
- **`sel` outlet 1 passes values, not bangs.** When using `sel N` for edge
  detection (e.g. in `cap-trigger.pd`), outlet 1 passes the non-matching value
  through. Use `t b` to strip it if you need a pure bang for triggering `f`.

## Deployment

`pd/` is excluded from `scripts/deploy.sh`. Copy individual Pd files to corazon
with `scp`:

```bash
scp pd/osc-receive.pd pd/cap-trigger.pd pd/heartbeat.pd corazon:shrine/pd/
```

`texture-test.pd` is edited in the Pd GUI on corazon. Copy it only when
replacing the entire patch.

## Remaining work

1. **Test texture-test.pd on target:** verify sfont~ note on/off, intensity CC11,
   heartbeat rate modulation with live sensor data or simulator.
2. **Heartbeat extraction:** bp~ at 1.2 Hz diverges numerically at audio sample
   rate. Needs a control-rate or decimated approach (accumulate samples, filter
   in a decimated domain). Currently stubbed to output 1.
3. **Jeanne initialization:** add loadbang → bank/pgm init (brent has this,
   jeanne currently requires manual Pgm selection).
4. **Drone detune wobble:** high-pass `cap-N` and feed the fluctuation into the
   drone partial detune (build-plan gotcha) — structure noted in `drone.pd`.
5. **Output:** tactile sends (`dac~ 5-8`, LPF ~80 Hz) in `master.pd`.
