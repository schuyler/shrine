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

#### Class library path fix (macOS)

On some macOS installations (observed with SC 3.14.1 via Homebrew cask),
`sclang` looks for the class library in `Contents/MacOS/SCClassLibrary` but
the files are actually in `Contents/Resources/SCClassLibrary`. The symptom is:

```
ERROR: There is a discrepancy.
numClassDeps 0   gNumClasses 82
ERROR: Library has not been compiled successfully.
```

Fix by creating `~/Library/Application Support/SuperCollider/sclang_conf.yaml`
with an explicit `includePaths` entry:

```yaml
includePaths:
  - /Applications/SuperCollider.app/Contents/Resources/SCClassLibrary
```

You may also need to clear the macOS quarantine flag after installing:

```sh
xattr -dr com.apple.quarantine /Applications/SuperCollider.app
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
sox -n -r 48000 -c 1 sc/samples/pad1.wav synth 10 sine 220.00 fade 0.5 10 0.5
sox -n -r 48000 -c 1 sc/samples/pad2.wav synth 10 sine 261.63 fade 0.5 10 0.5
sox -n -r 48000 -c 1 sc/samples/pad3.wav synth 10 sine 293.66 fade 0.5 10 0.5
sox -n -r 48000 -c 1 sc/samples/pad4.wav synth 10 sine 329.63 fade 0.5 10 0.5
```

This produces 10-second sine tones on an A minor pentatonic scale (A3, C4, D4,
E4), each with a 0.5-second fade in and out. The different pitches make it easy
to identify which pad is sounding, and the pentatonic intervals ensure the pads
sound harmonically compatible when played together.

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

`sc/controls.scd` opens a GUI panel for tweaking synth parameters in real
time. It is intended for sound design iteration and is not part of the
production boot sequence.

### Loading the panel

The controls panel requires the `sc3>` REPL prompt. Run `sclang` with no
arguments, then execute `startup.scd` and `controls.scd` in sequence:

```supercollider
thisProcess.interpreter.executeFile("/path/to/shrine/sc/startup.scd");
```

Wait for "Shrine startup complete." to appear, then:

```supercollider
thisProcess.interpreter.executeFile("/path/to/shrine/sc/controls.scd");
```

Loading `controls.scd` before startup finishes will open the window without
errors, but moving a slider will produce `DoesNotUnderstand` errors because
`~synths` has not been populated yet.

### What the controls do

The panel has 21 sliders across three sections. Each slider calls `.set()` on
the running synths; changes take effect immediately. All sliders initialize to
the SynthDef defaults.

**Pad Voices** — controls the granular synthesis engine for each pad. These
parameters shape how capacitive touch maps to sound.

| Slider | Default | Effect |
|--------|---------|--------|
| trigRateMin | 1 Hz | Grain trigger rate at zero touch (sparse) |
| trigRateMax | 40 Hz | Grain trigger rate at full touch (dense) |
| grainDurIdle | 0.3 s | Grain length at low touch (tonal) |
| grainDurFull | 0.05 s | Grain length at full touch (textural) |
| filterLo | 300 Hz | Low-pass cutoff at zero touch (dark) |
| filterHi | 8000 Hz | Low-pass cutoff at full touch (bright) |
| filterRq | 0.7 | Filter resonance — lower = sharper peak |
| gsrDrift | 0.1 | Pitch drift from neighboring GSR (±10%) |
| posSpeedMin | 0.1 Hz | Buffer scan speed at low touch |
| posSpeedMax | 2 Hz | Buffer scan speed at full touch |

**Collective Voices** — controls the additive sine clusters that emerge from
GSR connections between pads. There are 6 pair voices (one per pair of pads)
and 4 triad voices (one per combination of three pads). These sliders set the
same parameters on all 10 collective voices simultaneously.

| Slider | Default | Effect |
|--------|---------|--------|
| baseFreqMin | 40 Hz | Fundamental frequency at zero GSR |
| baseFreqMax | 120 Hz | Fundamental frequency at max GSR |
| collFilterLo | 200 Hz | Low-pass cutoff when phases are incoherent |
| collFilterHi | 4000 Hz | Low-pass cutoff when phases are coherent |
| gsrActiveThreshold | 0.1 | GSR below this counts as inactive |

**Output Mixer** — controls how each pad's output channel blends its granular
voice with the collective voices routed to it, plus reverb.

| Slider | Default | Effect |
|--------|---------|--------|
| collMixMin | 0.1 | Collective blend at low GSR |
| collMixMax | 0.6 | Collective blend at high GSR |
| revMixMin | 0.05 | Reverb wet/dry at low GSR |
| revMixMax | 0.4 | Reverb wet/dry at high GSR |
| reverbDamp | 0.5 | High-frequency damping in reverb tail |
| reverbRoom | 0.7 | Reverb room size (longer decay) |

Three buttons at the bottom open the scope, meter, and node tree views.

Closing the window does not affect the synths. Run the simulator
(`uv run python osc-sim/generator.py --manual` or the automatic arc) so there
is audio to hear while adjusting parameters.

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
