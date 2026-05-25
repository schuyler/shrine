# Testing the SuperCollider Sound Engine on macOS

The sound engine receives OSC sensor data and produces 4-channel audio. On
macOS, CoreAudio is used by default — no JACK required. This guide covers
getting the engine running locally with synthesized sensor data.

## Prerequisites

### SuperCollider

Install via Homebrew:

```sh
brew install --cask supercollider
```

Or download from [supercollider.github.io](https://supercollider.github.io/downloads).

The `sclang` binary must be on your `$PATH`. After a cask install it is at
`/Applications/SuperCollider.app/Contents/MacOS/sclang`; add it to your PATH
or create a symlink:

```sh
ln -s /Applications/SuperCollider.app/Contents/MacOS/sclang /usr/local/bin/sclang
```

### sox

```sh
brew install sox
```

Used to generate placeholder sample files.

### Python dependencies

The OSC simulator uses `uv`. From the repo root:

```sh
uv sync
```

## Generating Placeholder Samples

The engine loads four mono 48 kHz WAV files from `sc/samples/pad{1-4}.wav`.
These files are not in the repository. Generate test tones before starting
the engine:

```sh
mkdir -p sc/samples
for i in 1 2 3 4; do
    sox -n -r 48000 -c 1 sc/samples/pad${i}.wav synth 10 sine $((200 + i * 100)) fade 0.5 10 0.5
done
```

This produces 10-second sine tones at 300, 400, 500, and 600 Hz, each with a
0.5-second fade in and out. The different frequencies make it easy to identify
which pad is sounding.

## Running the Sound Engine

From the repo root:

```sh
sclang sc/startup.scd
```

Startup proceeds in five phases. Expected console output:

```
Phase 1: config loaded.
Phase 2: buses allocated.
Phase 3: OSC handlers registered.
Phase 4: palette SynthDefs loaded.
Phase 5: routing complete.

Shrine startup complete.
```

Each phase line appears as that phase completes. The `s.sync` calls in phases
4 and 5 can take a second or two while the server compiles SynthDefs and loads
buffers.

### 4-channel audio on stereo hardware

The engine requests 4 output channels (`numOutputBusChannels = 4`). CoreAudio
on built-in speakers or standard headphones provides 2. SC will not crash —
channels 2 and 3 are silently ignored. Channels 0 and 1 (left and right) are
audible on stereo headphones and are sufficient for testing.

SC defaults to 44100 Hz internally. The samples are 48000 Hz. SC resamples
automatically; no action required.

## Feeding Sensor Data

In a second terminal, run the OSC simulator from the repo root.

**Automatic scenario arc** (recommended first test):

```sh
uv run python osc-sim/generator.py
```

Plays through a scripted arc: sensor values start at zero and ramp up over
roughly 30–60 seconds. You should hear silence at first, then pads emerging
gradually, with character shifting as capacitance and GSR values increase
(more reverb, increased collective voice blending at higher GSR levels).

**Interactive mode**:

```sh
uv run python osc-sim/generator.py --manual
```

Presents a curses UI with sliders for each pad's capacitance and GSR values.
Moving a slider produces an immediate audio change in the corresponding pad
voice. This is the fastest way to check that OSC routing is working correctly.

Additional options:

| Flag | Default | Description |
|------|---------|-------------|
| `--host HOST` | `127.0.0.1` | OSC destination address |
| `--port PORT` | `57120` | OSC destination port |
| `--rate HZ` | `100` | Packets per second |
| `--scenario NAME` | `default` | Named arc to play (automatic mode) |

## Live Controls GUI

`sc/controls.scd` opens a GUI panel for tweaking synth parameters in real time. It is intended for sound design iteration and is not part of the production boot sequence.

Load it after startup completes (after "Shrine startup complete." appears) by executing at the `sc3>` prompt. Loading before startup finishes will open the window without errors, but moving a slider will produce `DoesNotUnderstand` errors because `~synths` has not been populated yet.

```supercollider
thisProcess.interpreter.executeFile("/path/to/shrine/sc/controls.scd");
```

The panel opens a window titled "Shrine Controls" with 21 EZSliders across three sections:

**Pad Voices** — `trigRateMin`, `trigRateMax`, `grainDurIdle`, `grainDurFull`, `filterLo`, `filterHi`, `filterRq`, `gsrDrift`, `posSpeedMin`, `posSpeedMax`

**Collective Voice** — `baseFreqMin`, `baseFreqMax`, `collFilterLo`, `collFilterHi`, `gsrActiveThreshold`

**Output Mixer** — `collMixMin`, `collMixMax`, `revMixMin`, `revMixMax`, `reverbDamp`, `reverbRoom`

Each slider calls `.set()` on the running synths; changes take effect immediately. All sliders initialize to the SynthDef defaults, so the starting state matches the engine running without the panel.

Three buttons at the bottom open the scope, meter, and node tree views.

Closing the window does not affect the synths. Run the simulator (`uv run python osc-sim/generator.py --manual` or the automatic arc) so there is audio to hear while adjusting parameters.

## Verifying OSC Data Without Audio

To confirm OSC data is arriving and reaching the control buses, poll a bus
value from the `sc3>` prompt while the simulator is running:

```supercollider
~buses[\cap][0].get({ |v| ("cap[0] = " ++ v).postln });
```

With the simulator active, this should print a non-zero value. Repeat at
intervals to watch the value change. `~buses[\cap]` is an array of four buses
(one per pad); index 0–3 maps to pads 0–3.

## Troubleshooting

**`WARNING: pad1.wav failed to load or is empty`**

The sample file is missing or has zero frames. Run the `sox` generation
command above, then restart sclang.

**No sound**

Check the post window for audio device errors. If SC selected the wrong output
device, set it explicitly before starting:

```supercollider
Server.default.options.outDevice = "Built-in Output";
```

Run this at the `sc3>` prompt before launching `startup.scd`, or add it to the
top of `startup.scd` above the `s = Server.default` line.

**`ERROR: SynthDef not found`**

Startup did not complete. Check the post window for syntax errors or server
boot failures. Common causes: the server failed to boot (port conflict, audio
device not available) or a `.scd` file has a syntax error.

**OSC data not arriving**

`startup.scd` opens UDP port 57120 explicitly with `thisProcess.openUDPPort(57120)`.
If the port is already in use by another process, the OSC handlers will not
receive data. Check with:

```sh
lsof -i udp:57120
```

Quit any conflicting process, then restart sclang.

**Quitting sclang**

Press `Ctrl+C`, or type at the prompt:

```supercollider
0.exit
```
