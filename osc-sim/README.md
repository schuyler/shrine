# osc-sim

OSC sensor-data simulators for developing the Shrine sound engine and LED
engine without the physical edge nodes. Both tools emit the exact firmware
contract: one `/shrine/node/N` message per node (N = 0–3), each with five
floats — `self_stdev`, `self_carrier_mag`, and three `gsr_mag` cross-couplings
(see `edge-node/README.md`, "OSC Output").

## `manual.py` — hands-on control

A fully manual simulator: every one of the 20 OSC floats (4 nodes × 5
channels) is an independent slider you drive from the keyboard, so you can pose
any sensor state and hold it. Unlike the automated tool, nothing changes unless
you change it. Mute is non-destructive — `x` mutes one channel and `t`
touches/releases a whole node (a "user"), both keeping the dialed-in levels so
you can simulate people touching and letting go without re-posing.

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
| `t` | touch / release the selected node — mute all its channels at once |
| `n` / `m` | zero / max the whole selected node |
| `z` / `f` | zero / fill every channel |
| `s` | toggle smoothing (eased transitions vs. instant) |
| `J` | toggle organic jitter (subtle noise layered on held values) |
| `q` | quit |

Useful flags: `--rate HZ` (default 30), `--no-smoothing`, `--jitter`.

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
