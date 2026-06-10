# Design: Diatonic Mode Progression

Runtime switching of the tonal mode in response to conductor state changes,
implementing the agreed modal arc for the Shrine installation.

## Modal Arc

| State (int) | State name  | Mode symbol      | Intervals (semitones from root) | Size |
|-------------|-------------|------------------|---------------------------------|------|
| 0 quiet     | quiet       | major-penta      | 0 2 4 7 9                       | 5    |
| 1 seeking   | seeking     | major-penta      | 0 2 4 7 9                       | 5    |
| 2 aligning  | aligning    | dorian           | 0 2 3 5 7 9 10                  | 7    |
| 3 energizing| energizing  | mixolydian-b6    | 0 2 4 5 7 8 10                  | 7    |
| 4 ascending | ascending   | ionian           | 0 2 4 5 7 9 11                  | 7    |

Mixolydian b6 (melodic minor mode 5, a.k.a. "Hindu" scale): like mixolydian
but with a flatted 6th. The b7 + b6 combination produces the dark undertow
quality.

## Current State of the Code

### What already works

1. **`mode-table.pd`** receives `r scene-mode` (a symbol), routes it via
   `[route major-penta minor-penta ionian dorian phrygian lydian mixolydian aeolian]`,
   and fires a message that writes `mode-intervals` (array), sends `mode-size`
   (float), and bangs `mode-changed`. Loadbang sends `major-penta`. The table
   `mode-intervals` has size 7; pentatonic modes pad trailing positions with 0.

2. **`state-table.pd`** receives `r shrine-state` (int 0-4), maps to a mode
   symbol, sends on `s scene-mode`. Loadbang sends 0 (quiet = major-penta).

3. **`melodic-voice.pd`** (voice subpatch) converts scale degree to MIDI pitch
   using `[mod N]` / `[div N]` where N comes dynamically from `[r mode-size]`.
   The right inlets of `mod` and `div` update when `mode-size` changes. This
   means the degree-to-pitch mapping already handles variable mode sizes
   correctly at runtime.

4. **`melodic-voice.pd`** (range subpatch) computes the walk range as
   `floor(1.5 * mode-size)`. When mode-size changes from 5 to 7, range goes
   from 7 to 10 (approximately 1.5 octaves in either case). Note: the init
   subpatch hardcodes `$0-range = 7` as the startup default. This equals
   `floor(1.5 * 5) = 7`, which is correct for major-penta. If the default
   mode were changed to something other than a 5-note scale, this hardcoded
   value would need to be updated.

5. **`osc-receive.pd`** routes `/shrine/cue/state` through
   `[route quiet seeking aligning energizing ascending]` and converts to int
   0-4 on bus `shrine-state`. The conductor sends state names as lowercase
   strings.

### What needs to change

**`state-table.pd`** — Two mapping errors vs. the agreed arc:
- State 3 (energizing) currently sends `mixolydian`; must send `mixolydian-b6`
- State 4 (ascending) currently sends `lydian`; must send `ionian`

**`mode-table.pd`** — Missing mode:
- `mixolydian-b6` is not in the route list. Must be added with intervals
  `0 2 4 5 7 8 10`.
- The existing `mixolydian` entry (intervals `0 2 4 5 7 9 10`) can stay for
  completeness but is unused by the arc.

**`main.pd`** — Both `state-table` and `mode-table` must be instantiated.
The README flags the `scene-mode` connection as a "seam" because these
abstractions may not be loaded in `main.pd` yet. (Verify on target — main.pd
is GUI-edited on corazon and excluded from deploy.) If either is absent, all
7-note modes produce wrong MIDI pitches: `melodic-voice.pd` falls back to
`mod 5` / `div 5` and silently treats every mode as a 5-note scale.

## Exact Changes

### 1. state-table.pd — fix the arc mapping

Current wiring (sel outlets → msg boxes):

```
sel 0 → "major-penta"     (quiet)      — correct
sel 1 → "major-penta"     (seeking)    — correct (outlets 0+1 both to same msg)
sel 2 → "dorian"          (aligning)   — correct
sel 3 → "mixolydian"      (energizing) — WRONG, change to "mixolydian-b6"
sel 4 → "lydian"          (ascending)  — WRONG, change to "ionian"
```

Comment line (line 6 in the .pd file, the `#X text` with the arc listing) must
also be updated to reflect the correct mapping.

### 2. mode-table.pd — add mixolydian-b6

Add `mixolydian-b6` to the route list. The route becomes:

```
route major-penta minor-penta ionian dorian phrygian lydian mixolydian mixolydian-b6 aeolian
```

Add the corresponding message box:

```
; mode-intervals 0 0 2 4 5 7 8 10 ; mode-size 7 ; mode-changed bang
```

In Pd's semicolon-message syntax for arrays, the first argument after the
array name is the start index (here `0`), not a data value. The actual
interval data begins at the second number. So `mode-intervals 0 0 2 4 5 7 8
10` writes `[0, 2, 4, 5, 7, 8, 10]` starting at index 0.

(This is standard mixolydian with degree 5 changed from 9 to 8 — the b6.)

No other changes to mode-table.pd. The table stays at size 7. The `mode-size`
/ `mode-changed` / `mode-intervals` bus protocol is unchanged.

### 3. main.pd — ensure both abstractions are loaded

Verify (on corazon) that `main.pd` contains:
```
[mode-table]
[state-table]
```

If not, add them. No inlet/outlet connections needed — they communicate
entirely via named sends/receives (`scene-mode`, `shrine-state`,
`mode-intervals`, `mode-size`, `mode-changed`).

### 4. melodic-voice.pd — no changes

The voice subpatch's `mod` / `div` right inlets are already driven by
`r mode-size`. When mode-size jumps from 5 to 7 (or back), the degree→pitch
mapping updates automatically. The walk range also updates via the range
subpatch. No code changes needed.

## MIDI Note Content Per Mode

Root = 60 (middle C). The walk range of `floor(1.5 * mode-size)` degrees
determines the pitch span. Degree N maps to `root + intervals[N mod size] +
12 * (N / size)`.

### Major pentatonic (quiet/seeking) — mode-size 5, range 7

| Degree | 0  | 1  | 2  | 3  | 4  | 5  | 6  |
|--------|----|----|----|----|----|----|-----|
| MIDI   | 60 | 62 | 64 | 67 | 69 | 72 | 74  |
| Note   | C4 | D4 | E4 | G4 | A4 | C5 | D5  |

No semitone adjacencies. Interval content: M2, M2, m3, M2, m3.
Character: open, consonant, "safe."

### Dorian (aligning) — mode-size 7, range 10

| Degree | 0  | 1  | 2  | 3  | 4  | 5  | 6  | 7  | 8  | 9  |
|--------|----|----|----|----|----|----|----|----|----|----|
| MIDI   | 60 | 62 | 63 | 65 | 67 | 69 | 70 | 72 | 74 | 75 |
| Note   | C4 | D4 | Eb4| F4 | G4 | A4 | Bb4| C5 | D5 | Eb5|

b3 and b7 give minor quality; natural 6 keeps it warm (not dark like
aeolian). The b3 (Eb) is the first dissonance participants encounter after
pentatonic — it arrives when the group is already connecting.

### Mixolydian b6 (energizing) — mode-size 7, range 10

| Degree | 0  | 1  | 2  | 3  | 4  | 5  | 6  | 7  | 8  | 9  |
|--------|----|----|----|----|----|----|----|----|----|----|
| MIDI   | 60 | 62 | 64 | 65 | 67 | 68 | 70 | 72 | 74 | 76 |
| Note   | C4 | D4 | E4 | F4 | G4 | Ab4| Bb4| C5 | D5 | E5 |

Major 3rd (E) gives brightness. The b6 (Ab) and b7 (Bb) produce the
"gravity pull" — the descending Ab→G and Bb→(implied root) tensions that
create cinematic drama. The Ab-to-E tritone (degree 5 to degree 2 in the
next octave) is the most dissonant interval in the arc.

### Ionian (ascending) — mode-size 7, range 10

| Degree | 0  | 1  | 2  | 3  | 4  | 5  | 6  | 7  | 8  | 9  |
|--------|----|----|----|----|----|----|----|----|----|----|
| MIDI   | 60 | 62 | 64 | 65 | 67 | 69 | 71 | 72 | 74 | 76 |
| Note   | C4 | D4 | E4 | F4 | G4 | A4 | B4 | C5 | D5 | E5 |

Standard major scale. The natural 6 (A) and major 7 (B) resolve the
tensions of mixolydian b6. The leading tone (B→C) gives the sense of
arrival. Clean, resolved, luminous.

## Signal Flow Summary

Cold-start initialization path (before any conductor message arrives):

```
[osc-receive.pd] loadbang
    → sends 0 to s shrine-state

[state-table.pd]
    r shrine-state (0) → msg "major-penta" → s scene-mode

[mode-table.pd]
    r scene-mode ("major-penta") → writes mode-intervals array, sends mode-size 5
```

This is what puts the system into major pentatonic at boot without a
conductor message.

Runtime path:

```
[osc-receive.pd]
    /shrine/cue/state "aligning"
        → route quiet seeking aligning energizing ascending
        → msg 2
        → s shrine-state

[state-table.pd]
    r shrine-state  (int 2)
        → sel 0 1 2 3 4
        → outlet 2 → msg "dorian"
        → s scene-mode

[mode-table.pd]
    r scene-mode  (symbol "dorian")
        → route ... dorian ...
        → ; mode-intervals 0 0 2 3 5 7 9 10 ; mode-size 7 ; mode-changed bang
        (writes array, broadcasts mode-size, bangs mode-changed)

[melodic-voice.pd]  (all instances, via named receives)
    r mode-size  (7)
        → t f f → mod right inlet, div right inlet
        (next step uses the new mode-size for degree→pitch)

    r mode-changed  (bang)
        (not currently consumed — available for future use, e.g.,
         re-quantizing the current degree to the nearest note in the new mode)
```

## Risk Assessment

### Array write during read — race condition

**Risk: low.** Pd is single-threaded. The `mode-intervals` array write
happens in one message evaluation. No DSP-rate reads of this array exist —
`tabread mode-intervals` fires only when a step bang arrives. A step bang
and a mode-change message cannot interleave within a single Pd tick.

**However:** if a mode change arrives in the same logical tick as a step
bang, Pd's message ordering determines which executes first. The `r
mode-size` update and the `mode-intervals` array write are in the same
semicolon-separated message, so they execute atomically in order. A step
bang in the same tick would see either the old or new mode consistently,
never a partial update.

### Degree out of range after mode-size change

**Risk: medium.** When mode-size jumps from 5 to 7 (or 7 to 5), the stored
`$0-degree` and `$0-range` may be inconsistent:

- **5→7 (pentatonic → diatonic):** degree is in [0,7), range becomes 10.
  The degree is valid in the new range. Safe.

- **7→5 (diatonic → pentatonic):** degree could be in [0,10), range becomes
  7. A degree of 8 would `mod 5` = 3 and `div 5` = 1, giving
  `root + intervals[3] + 12` — a valid pitch. The boundary subpatch won't
  clamp until the next step. This produces a valid note, just potentially
  outside the intended range for one step.

**Mitigation:** Acceptable as-is. The walk self-corrects within one step
because the boundary reflection uses the updated range. In practice, mode
changes happen infrequently (state transitions take seconds), and the
one-step anomaly is inaudible.

In the current arc, the mode changes only go 5→7→7→7 (pentatonic →
dorian → mixolydian b6 → ionian). The 7→5 case only arises if the
conductor drops back to quiet/seeking after escalation — an unlikely
regression path, and harmless if it occurs.

### Exposed dissonance on transition

**Risk: medium (artistic, not technical).** When the mode switches, notes
already sounding (sfont~ envelope tails) are in the old mode while new
notes are in the new mode. This produces brief cross-mode dissonance.

**Mitigation options (ranked):**
1. **Accept it.** Transitions are rare, envelopes are short, and the
   dissonance reads as a "shift" moment. Likely fine for an installation.
2. **Send `mode-changed` to melodic-voice as a note-off.** Kill all
   sounding notes on mode change, ensuring a clean slate. Cost: a brief
   silence at transition (could feel like a dropout).
3. **Crossfade.** Not practical in the current architecture (single array,
   single voice chain).

Recommendation: start with option 1. If it sounds bad in testing, implement
option 2 (add `r mode-changed` → trigger note-off in melodic-voice's
voice subpatch).

### Drone layer unaffected

The additive drones (`drone.pd`) are frequency-based, not scale-based. They
are unaffected by mode changes. The drones provide a constant tonal anchor
in the root (C) regardless of mode — which is desirable.

## Testing

### Headless verification

Extend the existing `pd/test/melodytest.pd` pattern. A `modetest.pd` that:

1. Loads `mode-table` and `state-table`
2. Sequences shrine-state values 0→2→3→4 with delays
3. Drives a `melodic-voice` with a metro
4. Prints `MELODY pitch velocity` and `MODE-SIZE size` at each change
5. Verify: pitches stay within expected range per mode, mode-size changes are
   reflected in the mod/div behavior

Expected output per mode (root 60):
- major-penta: pitches in {60,62,64,67,69,72,74}
- dorian: pitches in {60,62,63,65,67,69,70,72,74,75}
- mixolydian-b6: pitches in {60,62,64,65,67,68,70,72,74,76}
- ionian: pitches in {60,62,64,65,67,69,71,72,74,76}

### Manual verification on target

After deploy, use the OSC simulator to send state changes:
```bash
# Send state transitions manually
uv run python -c "
from pythonosc.udp_client import SimpleUDPClient
c = SimpleUDPClient('corazon.local', 57120)
c.send_message('/shrine/cue/state', 'aligning')
"
```

Listen for the tonal shift in the melodic voices.

## Implementation Sequence

1. **main.pd** (prerequisite — do this first) — `main.pd` MUST contain
   `[state-table]` and `[mode-table]` objects. Without them, the feature
   silently fails: `melodic-voice.pd` defaults to `mod 5` / `div 5` and all
   7-note modes produce wrong MIDI pitches. Open main.pd on corazon and verify
   both objects are present. If either is absent, add it — no inlet/outlet
   connections are needed, as they communicate entirely via named sends/receives
   (`shrine-state`, `scene-mode`, `mode-intervals`, `mode-size`, `mode-changed`).
   Save and confirm before proceeding.
2. **state-table.pd** — Change the two message boxes: energizing → `mixolydian-b6`,
   ascending → `ionian`. Update the comment text.
3. **mode-table.pd** — Add `mixolydian-b6` to the route and add its message box
   with intervals `0 2 4 5 7 8 10`.
4. **melodytest update** — Add a mode-switch test patch.
5. **Deploy and test** — rsync, then exercise with the simulator.
