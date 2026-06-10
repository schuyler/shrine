# osc-sim

OSC sensor-data simulators for developing the Shrine sound engine and LED
engine without the physical edge nodes. Both tools emit the exact firmware
contract: one `/shrine/node/N` message per node (N = 0–3), each with five
floats — `self_stdev`, `self_carrier_mag`, and three `gsr_mag` cross-couplings
(see `edge-node/README.md`, "OSC Output").

## `manual.py` — hands-on control

A fully manual simulator you drive from the keyboard, so you can pose any sensor
state and hold it. Unlike the automated tool, nothing changes unless you change
it. The controls match the physical model the receiver reconstructs:

* **Presence** per node — `stdev` and `carrier`, independent (8 channels).
* **Couplings** per node *pair* — one GSR value per pair (6 channels). The
  firmware reports each pair from *both* nodes, so the simulator drives it from
  a single fader and writes it to both sides — set a coupling once and both
  nodes report it identically. Releasing a user zeroes its presence and every
  coupling it touches, on both sides.

Mute is non-destructive — `x` mutes one channel and `t` touches/releases a whole
node (a "user"), both keeping the dialed-in levels so you can simulate people
touching and letting go without re-posing.

```bash
uv run python osc-sim/manual.py --host localhost          # single target
uv run python osc-sim/manual.py --targets 255.255.255.255:57120 255.255.255.255:9000
```

Controls (also shown in the footer):

| Key | Action |
|-----|--------|
| arrows / `hjkl` | move the cursor between channels |
| `+` / `-` | raise / lower the selected channel by the step (0.05) |
| `]` / `[` | fine adjust by 0.01 |
| `0`–`9` | set the selected channel to 0.0 .. 0.9 |
| space | set the selected channel to 1.0 |
| `x` | mute / unmute the selected channel (keeps its dialed level) |
| `t` | touch / release the selected node (its presence + couplings) |
| `n` / `m` | zero / max the selected node (presence + its couplings) |
| `z` / `f` | zero / fill every channel |
| `s` | toggle smoothing (eased transitions vs. instant) |
| `J` | toggle organic jitter (subtle noise layered on held values) |
| `q` | quit |

Useful flags: `--rate HZ` (default 30), `--no-smoothing`, `--jitter`.

### Desktop GUI (`manual_gui.py`)

`manual_gui.py` is a Qt (PySide6) desktop front-end over the *same* state model
as `manual.py` — identical OSC, smoothing, jitter, mute and pair-symmetry
behaviour. PySide6 is an optional dependency, so install the `gui` group first:

```bash
uv sync --group gui
uv run --group gui python osc-sim/manual_gui.py --host localhost
```

Each node is a column with its `stdev`/`carrier` presence faders and a
**Release/Touch** button; the six GSR couplings are a row of faders below,
labelled by node pair (e.g. `0–1`). The label above a fader shows the live value
being sent; the slider sets the target. The `M` button mutes a single channel.
Global toggles for smoothing and jitter and `Zero all`/`Fill all` buttons sit
along the bottom. Same CLI flags as `manual.py`.

The GUI is fully keyboard-drivable with the same keys as the curses tool — a
highlighted cursor marks the selected channel:

| Key | Action |
|-----|--------|
| arrows / `hjkl` | move the selection cursor |
| `+` / `-` | adjust selected channel by 0.05 |
| `]` / `[` | fine adjust by 0.01 |
| `0`–`9` | set selected channel to 0.0 .. 0.9 |
| space | set selected channel to 1.0 |
| `x` | mute / unmute the selected channel |
| `t` | touch / release the selected node (presence channels) |
| `n` / `m` | zero / max the selected node (presence channels) |
| `z` / `f` | zero / fill every channel |
| `s` / `J` | toggle smoothing / jitter |
| `q` | quit |

## `generator.py` — automated scenario

Plays a scripted creative arc (Silence → Solo → … → Crescendo → Decay) with
organic noise. Good for exercising the engine end to end. It also has an
`alsamixer`-style `--manual` mode, but that mode collapses each node's `stdev`
and `carrier_mag` into a single value; use `manual.py` for independent control
of every channel.

```bash
uv run python osc-sim/generator.py --host localhost   # automated arc
```

## `monitor.py` — OSC logger

Prints every incoming OSC message; handy for confirming what a simulator (or
the firmware) is actually sending.

```bash
uv run python osc-sim/monitor.py --port 57120
```
