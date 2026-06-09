# Shrine Pure Data sound engine

Pure Data audio engine for the **Shrine of Inter-Dimensional Propitiation**. It
receives OSC from the four ESP32 sensor nodes and turns capacitive + GSR sensing
into sound. See the BSS wiki pages `Pd_Architecture`, `Voice_Architecture`,
`Pd_Build_Plan`, and `Sound_Design_Cookbook` for the full design.

The engine is intentionally **two engines split by layer**:

- **Additive drones** — four presence-drones (one per pad), cap-driven amplitude
  and detune. Continuous, per-partial, body-coupled. (`drone.pd`)
- **SoundFont melodic voices** — six connection-driven voices (one per GSR pair),
  note/rhythm/volume only, played through `[sfont~]`. (`melodic-voice.pd` +
  `sfont-host.pd`)

## The OSC contract (real, as wired here)

This is the contract actually emitted by `edge-node` firmware
(`network_task.c`) and `osc-sim/generator.py`, and consumed by `leds/` — **not**
the older contract some wiki pages described. It is the source of truth for this
code.

```
/shrine/node/{0..3}  ->  5 floats:
    [0] self_stdev    -> pad presence ("cap"); node N -> bus cap-(N+1)
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

**Value ranges:** the simulator sends cap≈0–1000 and gsr≈0–50 (mimicking firmware
ranges); `osc-receive` normalizes to 0–1 in `normcap` (÷1000) / `normgsr` (÷50).
Real firmware sends *calibrated* values — revisit these divisors against a live
node before deployment.

### Named buses

`osc-receive` publishes these via `[send]`; everything downstream `[receive]`s them:

- `cap-1` … `cap-4` (0–1) — per-pad presence
- `gsr-mag-0` … `gsr-mag-5` (0–1) — per-pair contact magnitude

There is **no per-pair GSR stdev** in the real data (the wiki's `gsr-std-0..5`
buses were never backed by a signal). The "restlessness" the design needs for
rhythmic subdivision is therefore **derived host-side** in `restless.pd` from the
fluctuation of an existing stream (cap or gsr-mag).

## Files

| File | Status | Purpose |
|------|--------|---------|
| `osc-receive.pd` | **verified** | OSC in → normalized `cap-*` / `gsr-mag-*` buses |
| `normcap.pd` / `normgsr.pd` | verified | ÷1000 / ÷50 then clip 0–1 |
| `nodevals.pd` | verified | unpack one node list → normalized cap + 3 gsr |
| `drone.pd` | **verified** | additive presence drone (inlet0 cap, inlet1 base Hz) |
| `master.pd` | verified (load) | per-channel soft-limit → `dac~ 1-4` |
| `clock.pd` | verified (load) | global pulse: `beat`, `bar`, `beat-ms` (default 60 BPM) |
| `mode-table.pd` | **verified** | fills `mode-notes` array (major pentatonic, MIDI 36–93) |
| `restless.pd` | **verified** | fluctuation proxy 0–1 (replaces absent gsr-stdev) |
| `melodic-voice.pd` | **verified** (note-gen) | per-pair walk → MIDI to `[s voice-midi]` |
| `heartbeat.pd` | verified | STUB: constant 60 BPM + 0 detune (per build plan) |
| `monitor.pd` | verified (load) | DEV-ONLY bus printer (do not load in production) |
| `main.pd` | verified (load) | top level: OSC + 4 drones + master |
| `sfont-host.pd` | **DRAFT** | `[sfont~]` host — needs ELSE + on-target verification |

"verified" = exercised headless under Pd 0.54 with the real OSC format / signal
measurement (see Testing). "verified (load)" = loads clean, components verified
individually. "DRAFT" = authored but not run (depends on ELSE `[sfont~]`).

`main.pd` currently wires the **additive drone slice** (OSC → cap → 4 drones →
master), which is fully verified. The SoundFont melodic layer is the next wiring
step (see Remaining work).

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

- **`[oscparse]` splits the address** into separate symbols (`shrine node 0 …`),
  and the numeric node id arrives as a **symbol**. Vanilla `[route]`/`[select]`
  won't match it against numeric args. `osc-receive` converts it via
  `[makefilename x%s] → [select x0 x1 x2 x3]`, then prepends a float and routes.
- **Abstraction `$`-args** work in `[send]`/`[receive]` *names* (`r cap-$1`) but
  **not as numeric values** (`[f $1]` yields 0). Pass values via inlets instead —
  that's why `drone` takes its base frequency on an inlet.
- **Commas and semicolons in `#X text` comments** must be escaped (`\,` `\;`) or
  Pd parses the tail as a separate message and throws "no method" errors.

## Remaining work

Mapping to `Pd_Build_Plan`'s phases:

1. **Melodic layer (build-plan Phase 1/3):** drop a GM choir/organ `.sf2` into
   `pd/samples/`, finish `sfont-host.pd` against the real `[sfont~]` message
   syntax, instantiate six `melodic-voice` in `main.pd` (register index + channel
   per pair via inlets), and verify on Pd 0.56 + ELSE.
2. **Subdivision:** drive `melodic-voice` step rate from `restless-*` via the
   subdivision ladder (per-bar commit + hysteresis). Currently steps once per beat.
3. **Walk polish:** reflect at window edges instead of `[clip]`; add note-off
   discipline so `[sfont~]` doesn't pile up stuck notes.
4. **Drone detune wobble:** high-pass `cap-N` and feed the fluctuation into the
   drone partial detune (build-plan gotcha) — structure noted in `drone.pd`.
5. **Heartbeat:** replace `heartbeat.pd` stub once the 1–3 Hz pulse signal is
   bench-validated.
6. **Output:** tactile sends (`dac~ 5-8`, LPF ~80 Hz) in `master.pd`.
