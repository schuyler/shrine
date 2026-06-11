# Shrine Pure Data sound engine

Pure Data sound engine for Shrine. It receives OSC from the four ESP32 sensor
nodes and turns capacitive + GSR sensing into sound. See the BSS wiki pages
`Pd_Architecture`, `Voice_Architecture`, `Pd_Build_Plan`, and
`Sound_Design_Cookbook` for the full design.

The engine is intentionally **two engines split by layer**:

- **Additive drones** — four presence-drones (one per pad), cap-driven amplitude
  and detune. Continuous, per-partial, body-coupled. (`drone.pd`)
- **SoundFont melodic voices** — connection-driven note *generators* (one per GSR
  pair), note/rhythm/volume only. Each `melodic-voice` is bang-triggered and emits
  a stream of `pitch velocity` pairs into a **texture renderer**'s `Note` inlet;
  the texture owns its own `[sfont~]` + effects (see `texture-test.pd`).
  (`melodic-voice.pd`)

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

**Value ranges:** firmware sends calibrated 0–1 values (normalized on-device).
The simulator matches this range. All values arrive as 0–1 floats; no divisor
abstractions are needed in Pd.

### Named buses

`osc-receive` publishes these via `[send]`; everything downstream `[receive]`s them:

- `cap-1` … `cap-4` (0–1) — per-pad presence
- `gsr-mag-0` … `gsr-mag-5` (0–1) — per-pair contact magnitude

There is **no per-pair GSR stdev** in the real data (the wiki's `gsr-std-0..5`
buses were never backed by a signal). The "restlessness" the design needs for
rhythmic subdivision is therefore **derived host-side** in `restless.pd` from the
fluctuation of an existing stream (cap or gsr-mag).

### Conductor cue buses

The `leds/` conductor state machine fans cue events to Pd on the **same OSC
port** (`/shrine/cue/*` → `--pd-port`, default 57120). `osc-receive` binds that
port once and routes both streams off the single `[osc.receive]` (one UDP bind —
two patches binding 57120 would contend, not both receive). It publishes:

- `shrine-state` (int 0–4) — current scene from `/shrine/cue/state`:
  `0 quiet · 1 seeking · 2 aligning · 3 energizing · 4 ascending`. Edge-triggered
  by the conductor; `osc-receive` `[loadbang]`s **0 (quiet)** so the engine
  cold-starts into the same state the FSM boots into. A mid-show Pd restart sits
  in quiet until the next organic transition (accepted).
- `shrine-group` (list of ints) — connected pad IDs in the largest component,
  from `/shrine/cue/group`. **Informational only** for now (printed in
  `monitor.pd`); not wired to sound. Its *size* is what drives the FSM's
  escalation upstream.
- `shrine-root` (int MIDI, default 36) — the melodic tonic for the **whole
  piece**, from `/shrine/cue/root <midi>`. Each `melodic-voice` transposes it by
  its own octave (effective root = `shrine-root + 12·octave`; the textures take
  octaves 0/1/2). `osc-receive` `[loadbang]`s **36** so the engine cold-starts
  in a defined key. Send e.g. `/shrine/cue/root 48` to move the whole piece up a
  fourth live. The conductor picks a fresh pentatonic tonic on each transition
  to quiet.
- `bpm` (float) — the global tempo, from `/shrine/cue/tempo <bpm>`. The
  conductor sends it at ~1 Hz (50–100 BPM, derived from FSM state + bucket
  fill). `main.pd` feeds `[r bpm]` into `clock.pd`, so Pd's `beat`/`bar`/
  `beat-ms` pulse **follows the conductor's tempo** rather than free-running at
  its 60 BPM default. The conductor is the tempo master; Pd's clock is a
  follower.

## Files

| File | Purpose |
|------|---------|
| `osc-receive.pd` | OSC in → `cap-*` / `gsr-mag-*` buses + conductor `shrine-state` / `shrine-group` |
| `drone.pd` | additive presence drone (inlet0 cap, inlet1 base Hz) |
| `master.pd` | per-channel soft-limit → `dac~ 1-4` |
| `clock.pd` | global pulse: `beat`, `bar`, `beat-ms`; inlet = BPM, driven by `[r bpm]` from `/shrine/cue/tempo` (60 BPM default until first cue) |
| `state-table.pd` | maps `shrine-state` int (0–4) → mode symbol on `s scene-mode`; arc: quiet/seeking → major-penta, aligning → dorian, energizing → mixolydian-b6, ascending → ionian |
| `mode-table.pd` | routes `scene-mode` symbol → writes `mode-intervals` array + `mode-size` + `mode-changed`; handles 9 modes including `mixolydian-b6` |
| `restless.pd` | fluctuation proxy 0–1 (derived from cap or gsr-mag, replaces absent gsr-stdev) |
| `melodic-voice.pd` | inlet0 bang advances the walk (+ `octave N` msg); inlet1 velocity 0–1 (from cap-trigger). Common tonic via `[r shrine-root]`, effective root = `shrine-root + 12·octave`. Emits `pitch velocity` pairs → texture `Note` inlet |
| `heartbeat.pd` | STUB: constant 60 BPM + 0 detune |
| `monitor.pd` | DEV-ONLY bus printer (do not load in production) |
| `main.pd` | top level: OSC + 4 drones + master |
| `texture-test.pd` | per-voice instruments (each embeds its own `[else/sfont~]` + FX), driven by a `Note` inlet expecting `pitch velocity` pairs |
| `test/modetest.pd` | headless test: sequences shrine-state 0–4, prints STATE-MODE / MODE-SIZE / INTERVAL-0..6 for each state |
| `test/run_modetest.py` | Python driver for `modetest.pd`; parses Pd stderr and checks mode symbols, sizes, and intervals against the design arc |

## Running

Target platform is **Pd 0.56+ with the ELSE library** (for `[sfont~]`):
on Debian 13, install Pd from `trixie-backports` and ELSE via Deken (see
`Pd_Build_Plan`). Vanilla parts run on Pd ≥ 0.51.

Dev (GUI, with the simulator). The simulator now defaults to the conductor's
port (`9001`), matching production — so run the conductor too and let it relay
`/shrine/node/*` on to Pd:

```bash
pd -path pd pd/main.pd            # open the engine (binds 57120)
uv run python -m leds.conductor   # binds 9001, relays node stream → Pd:57120
uv run python osc-sim/generator.py --host localhost   # automated sensor data
uv run python osc-sim/manual.py    --host localhost   # hands-on sensor data
```

To exercise Pd standalone (no conductor), aim the simulator straight at Pd's
bind with `--port 57120`.

Production (headless), per `Pd_Architecture`:

```bash
pd -nogui -rt -audioapi alsa -r 48000 -outchannels 4 \
   -audiooutdev "USB Audio" -path pd pd/main.pd
```

## Testing (headless)

The patches are validated by loading them under `pd -nogui -noaudio -stderr` and
either driving real OSC at them or measuring DSP with `env~`/`snapshot~`, with a
`[delay]→; pd quit` to self-terminate. Example — end-to-end OSC contract check:

```bash
pd -nogui -noaudio -stderr -path pd pd/test/osctest.pd &   # prints each bus
uv run python pd/test/send_nodes.py                        # sends /shrine/node/*
```

Melodic note generator (self-contained, no OSC needed) — loads `mode-table`
for the scale and toggles a `metro`-driven 1/0 touch/release gate into
`note-send`, which advances one `melodic-voice` and gates its pitches into
note-on/note-off pairs (intensity fixed at 0.7 for velocity). Prints each
`pitch velocity` pair before quitting after ~3 s:

```bash
pd -nogui -noaudio -stderr -path pd pd/test/melodytest.pd
```

Expect `print: MELODY <pitch> <velocity>` lines: a first note-on, then
alternating `<prev> 0` (note-off) / `<new> <vel>` (note-on) pairs as the walk
steps. Pitches should stay within ~1.5 octaves of MIDI 60 and on the major
pentatonic (60, 62, 64, 67, 69, …). Requires Pd vanilla only (no ELSE).

Mode progression (state-table + mode-table) — sequences shrine-state 0–4 and
verifies each state emits the correct mode symbol, mode-size, and interval
array:

```bash
uv run python pd/test/run_modetest.py
```

Expected: state 0–1 → major-penta (size 5), state 2 → dorian (size 7),
state 3 → mixolydian-b6 (size 7, intervals 0 2 4 5 7 8 10),
state 4 → ionian (size 7). Requires Pd vanilla only (no ELSE).

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
