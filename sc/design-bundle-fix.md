# Design: Bundle OSC-to-scsynth Writes to Fix FIFO Overflow

## Problem

The simulator runs at 30 Hz and sends 16 OSC messages per tick (4 cap, 6 GSR mag, 6 GSR
phase). Each message handler issues an individual `s.sendMsg(\c_set, ...)` call to
scsynth. That produces 480 server commands/sec, which overflows scsynth's command FIFO
during overnight runs.

## Solution Overview

Three changes, taken together:

1. Make `~buses[\cap]` a contiguous 4-channel allocation so all three sensor bus groups
   are addressable with `\c_setn` (set N consecutive buses in one command).
2. Replace per-message server writes in the simulator path with accumulator arrays and a
   30 Hz flush `Routine` that sends one `s.sendBundle` per tick containing three `\c_setn`
   commands.
3. Wrap the per-node server writes in the edge-node path in a single `s.sendBundle` per
   message (no accumulation needed there).

Result: simulator path drops from 480 commands/sec to 30 bundles/sec. Edge-node path
drops from up to 7 commands per `/shrine/node/N` message to 1 bundle.

---

## Change 1: Contiguous Cap Bus Allocation

### What changes

`sc/buses.scd` line 4: replace the 4-element `collect` with a single multi-channel
allocation.

### Why

`\c_setn` takes a base bus index and a flat array of values. It works for GSR already
because `~buses[\gsrMag]` and `~buses[\gsrPhase]` are each a single `Bus.control(s, 6)`,
so their channels are contiguous. Cap buses are currently 4 independent
`Bus.control(s, 1)` allocations. The server allocates these sequentially at startup in
practice, but nothing guarantees they are contiguous, and they cannot be treated as a
single `\c_setn` target without that guarantee. Making them one `Bus.control(s, 4)`
provides the guarantee.

### All cap bus references and required updates

| File | Location | Current | Updated |
|------|----------|---------|---------|
| `buses.scd` | line 4 | `4.collect({ Bus.control(s, 1) })` | `Bus.control(s, 4)` |
| `buses.scd` | line 24 | `.do` iterating over array of Bus objects | `.do` iterating over channel offsets |
| `osc-input.scd` | line 6 | `~buses[\cap][i].set(msg[1])` | write to accumulator (Change 2) |
| `osc-input.scd` | line 36 | `~buses[\cap][nodeId].set(msg[1])` | `s.sendMsg(\c_set, ~buses[\cap].index + nodeId, msg[1])` (Change 3) |
| `routing.scd` | line 48 | `~buses[\cap][i].index` | `~buses[\cap].index + i` |

The `TESTING.md` interactive snippet `~buses[\cap][0].get(...)` will break. Its updated
form is shown in the documentation section below.

### Code sketch — buses.scd

```supercollider
// Before:
~buses[\cap] = 4.collect({ Bus.control(s, 1) });

// After:
// 4 consecutive capacitive touch buses (one per pad), 0-indexed.
// Consecutive allocation is REQUIRED for \c_setn in the flush timer.
// Individual pad: ~buses[\cap].index + padIndex
~buses[\cap] = Bus.control(s, 4);
```

Debug print update (line 24):

```supercollider
// Before:
~buses[\cap].do({ |b, i| ("  cap[" ++ i ++ "] = bus " ++ b.index).postln });

// After:
4.do({ |i| ("  cap[" ++ i ++ "] = bus " ++ (~buses[\cap].index + i)).postln });
```

### Code sketch — routing.scd line 48

```supercollider
// Before:
\capBus, ~buses[\cap][i].index,

// After:
\capBus, ~buses[\cap].index + i,
```

---

## Change 2: Simulator Accumulate-and-Flush

### What changes

`sc/osc-input.scd`, simulator path (lines 1–21): OSCdefs write incoming values into
accumulator arrays instead of calling `s.sendMsg`. A 30 Hz `Routine` on `SystemClock`
flushes all three accumulators to scsynth in a single `s.sendBundle`.

### Why

The simulator tick rate and the flush rate are both 30 Hz. Each flush sends the most
recent values for all 16 channels. Under steady-state operation this is lossless:
each OSCdef fires once per tick, the flush fires once per tick, and the flush reads
whatever the OSCdefs wrote. If an OSCdef fires multiple times before a flush (e.g. the
flush skips a tick), the accumulator holds the latest value — that is the correct
behavior for a sensor feed.

### Accumulator design

Three module-level arrays, initialized to zero, one entry per channel:

```
~simAccum = IdentityDictionary.new;
~simAccum[\cap]      = Array.newClear(4).fill(0.0);   // indices 0–3
~simAccum[\gsrMag]   = Array.newClear(6).fill(0.0);   // indices 0–5
~simAccum[\gsrPhase] = Array.newClear(6).fill(0.0);   // indices 0–5
```

These are written from OSCdef callbacks (which run on the OSC thread) and read from the
flush Routine (which runs on SystemClock). SuperCollider's OSC callbacks and
SystemClock tasks do not run concurrently on the same thread, so there is no data-race
hazard between a write and a read in the SC language layer. The server-side update is
always atomic (one `\c_setn` command).

### Code sketch — simulator OSCdefs (osc-input.scd lines 3–21)

```supercollider
// Accumulator arrays for simulator flush
~simAccum = IdentityDictionary.new;
~simAccum[\cap]      = 4.collect({ 0.0 });
~simAccum[\gsrMag]   = 6.collect({ 0.0 });
~simAccum[\gsrPhase] = 6.collect({ 0.0 });

// --- Simulator format handlers (accumulate only, no server writes) ---
// Pad numbers are 1-indexed in the simulator protocol.
4.do({ |i|
    var padNum = i + 1;
    OSCdef(("simCap" ++ padNum).asSymbol, { |msg|
        ~simAccum[\cap][i] = msg[1];
    }, "/pad/" ++ padNum ++ "/cap");
});

~config[\gsrPairs].do({ |pair, idx|
    var i = pair[0], j = pair[1];

    OSCdef(("simGsrMag" ++ i ++ "_" ++ j).asSymbol, { |msg|
        ~simAccum[\gsrMag][idx] = msg[1];
    }, "/gsr/" ++ i ++ "/" ++ j);

    OSCdef(("simGsrPhase" ++ i ++ "_" ++ j).asSymbol, { |msg|
        // Simulator already sends 0..2pi; store as-is.
        ~simAccum[\gsrPhase][idx] = msg[1];
    }, "/gsr/" ++ i ++ "/" ++ j ++ "/phase");
});
```

### Code sketch — flush Routine

```supercollider
// 30 Hz flush routine: sends one bundle containing three \c_setn commands.
// Stored in ~simFlushRoutine so it can be stopped cleanly.
~simFlushRoutine = Routine({
    loop({
        s.sendBundle(nil,
            [\c_setn, ~buses[\cap].index,      4, *~simAccum[\cap]],
            [\c_setn, ~buses[\gsrMag].index,   6, *~simAccum[\gsrMag]],
            [\c_setn, ~buses[\gsrPhase].index, 6, *~simAccum[\gsrPhase]]
        );
        (1/30).wait;
    });
}).play(SystemClock);
```

Notes on the `s.sendBundle` call:
- First argument `nil` means "send immediately" (no timestamp offset).
- Each array element is an OSC message. The `*` spread operator flattens the accumulator
  array into positional arguments: `[\c_setn, baseIndex, count, val0, val1, ...]`.
- All three `\c_setn` commands are packed into one UDP datagram, which is what reduces
  the FIFO pressure.

---

## Change 3: Edge-Node Handler Bundling

### What changes

`sc/osc-input.scd`, edge-node path (lines 31–49): wrap the per-node `s.sendMsg` calls
in a single `s.sendBundle(nil, ...)`.

### Why

Each `/shrine/node/N` message already carries all values for that node. No accumulation
is needed. Bundling the resulting server commands collapses up to 7 individual `s.sendMsg`
calls (1 cap set + up to 6 GSR sets) into one UDP datagram.

For node 3, which has all 3 GSR slots active, the existing code sends:
- 1 `\c_set` for cap
- 3 `\c_set` for GSR mag
- 3 `\c_set` for GSR phase
= 7 commands

After this change: 1 bundle with up to 7 messages inside.

### Code sketch — osc-input.scd edge-node path

```supercollider
// --- Edge node format handlers ---
// /shrine/node/N sends 7 floats:
//   msg[1] = self_cap_mag
//   msg[2..4] = gsr_mag[0..2]
//   msg[5..7] = gsr_phase[0..2]
//
// Edge nodes send phase as atan2(Q,I) in -pi..pi. Normalize to 0..2pi
// so downstream code (pair/triad voices, output_mixer) sees a consistent range.
4.do({ |nodeId|
    OSCdef(("edgeNode" ++ nodeId).asSymbol, { |msg|
        var mapping = ~config[\nodeGsrMapping][nodeId];
        var bundle = Array.new;

        // msg[1] = self_cap_mag
        bundle = bundle.add([\c_set, ~buses[\cap].index + nodeId, msg[1]]);

        // msg[2..4] = gsr_mag[0..2], msg[5..7] = gsr_phase[0..2]
        mapping.do({ |globalIdx, localIdx|
            if(globalIdx.notNil, {
                var rawPhase = msg[5 + localIdx];
                var normPhase = if(rawPhase < 0, { rawPhase + (2 * pi) }, { rawPhase });
                bundle = bundle.add([\c_set, ~buses[\gsrMag].index + globalIdx, msg[2 + localIdx]]);
                bundle = bundle.add([\c_set, ~buses[\gsrPhase].index + globalIdx, normPhase]);
            });
        });

        s.sendBundle(nil, *bundle);
    }, "/shrine/node/" ++ nodeId);
});
```

The `*bundle` spread passes each element of `bundle` as a separate OSC message argument
to `sendBundle`. This is the standard SC idiom for building a bundle from a dynamic list
of messages.

---

## Flush Timer Lifecycle

### Startup

The flush Routine is created and started at the end of `osc-input.scd`, after all OSCdefs
are registered. `SystemClock` is available before `s.waitForBoot` completes, but the
Routine references `s` and `~buses`, which require the server to be up and buses to be
allocated. Since `osc-input.scd` is executed inside `startup.scd`'s `s.waitForBoot`
Routine (Phase 3, after Phase 2 allocates buses), the ordering is safe.

The Routine handle is stored in `~simFlushRoutine` so it can be inspected or stopped from
the REPL.

### Stopping

```supercollider
~simFlushRoutine.stop;
```

This is a clean stop: the Routine finishes its current `wait` sleep and does not execute
another flush cycle. The accumulator arrays remain in memory but are harmless. OSCdefs
continue to write to the accumulators; those writes are silently discarded until the
Routine is restarted or the system is restarted.

### Restarting after a server reboot

If scsynth crashes and restarts mid-session, `~buses` will have stale indices. The full
startup sequence must be re-run. The Routine does not need special handling for this case
beyond normal startup.

### No flush during startup

The Routine starts after `osc-input.scd` finishes executing. Synth instantiation
(routing.scd, Phase 5) happens after that. There is a window between Phase 3 (Routine
starts) and Phase 5 (synths created) where the Routine is sending `\c_setn` commands that
target buses which exist but have no synths reading them yet. This is harmless — bus
writes with no readers are silent no-ops.

---

## Files Modified and Summary of Changes

### `sc/buses.scd`

- Line 4: `4.collect({ Bus.control(s, 1) })` → `Bus.control(s, 4)`
- Line 24: debug print loop updated to use `.index + i` offset arithmetic

### `sc/osc-input.scd`

- Lines 3–21 (simulator handlers): OSCdefs rewritten to write into `~simAccum` arrays
  instead of calling `s.sendMsg`. Accumulator initialization block added before the
  OSCdefs.
- After line 21: `~simFlushRoutine` Routine added.
- Lines 31–49 (edge-node handlers): `s.sendMsg` calls replaced with `s.sendBundle` using
  dynamically-built bundle array.
- Line 36: `~buses[\cap][nodeId].set(msg[1])` updated to
  `[\c_set, ~buses[\cap].index + nodeId, msg[1]]` (added to bundle).

### `sc/routing.scd`

- Line 48: `~buses[\cap][i].index` → `~buses[\cap].index + i`

### `sc/TESTING.md` (documentation update, not a code change)

The interactive bus-polling snippet references `~buses[\cap][0]`, which no longer exists
after Change 1. Update to:

```supercollider
// Before (broken after Change 1):
~buses[\cap][0].get({ |v| ("cap[0] = " ++ v).postln });

// After:
Bus.new(\control, ~buses[\cap].index + 0, 1, s).get({ |v| ("cap[0] = " ++ v).postln });
// Or more directly:
s.getControlBusValues(~buses[\cap].index, 4, { |vals| vals.do({ |v, i| ("cap[" ++ i ++ "] = " ++ v).postln }) });
```

---

## Edge Cases and Risks

### Accumulator and flush are on different threads

SC's OSC callbacks run on the OSC receive thread; SystemClock Routines run on the clock
thread. A cap accumulator write and a flush read of the same slot can technically
interleave at the SC language level. In practice, SC's language runtime is single-threaded
from the user perspective (the interpreter processes one event at a time), but this
assumption should be noted. If a partial update is observed in testing, the mitigation is
to snapshot the accumulator into a local variable at the top of the flush loop:

```supercollider
var capSnap      = ~simAccum[\cap].copy;
var gsrMagSnap   = ~simAccum[\gsrMag].copy;
var gsrPhaseSnap = ~simAccum[\gsrPhase].copy;
s.sendBundle(nil,
    [\c_setn, ~buses[\cap].index,      4, *capSnap],
    [\c_setn, ~buses[\gsrMag].index,   6, *gsrMagSnap],
    [\c_setn, ~buses[\gsrPhase].index, 6, *gsrPhaseSnap]
);
```

This is the safer form and is recommended even though the race is unlikely.

### Bundle size

A bundle with three `\c_setn` messages carrying 4 + 6 + 6 = 16 float32 values plus OSC
framing is well under the default UDP MTU (1500 bytes). No fragmentation risk.

### `s.sendBundle(nil, *bundle)` with an empty bundle

For Node 0, `~config[\nodeGsrMapping][0]` is `[nil, nil, nil]`, so no GSR messages are
added to the bundle. The bundle will contain exactly one message (the cap set). This is
valid. If `mapping.do` produces zero non-nil entries and the cap write is somehow also
skipped (not currently possible given the code structure), an empty bundle would be sent,
which is a no-op. Not a risk under current logic.

### Clock drift in flush Routine

`SystemClock` uses wall time. `(1/30).wait` will drift slightly over an overnight run.
This is acceptable — the flush rate just needs to be fast enough to keep up with the
simulator tick rate; sub-millisecond precision is not required.

### Simulator OSCdefs still fire when edge-node mode is active

The simulator and edge-node OSCdefs are both registered unconditionally. In edge-node
mode, no simulator messages arrive, so the simulator OSCdefs never fire and the flush
Routine runs but sends the initial zero values repeatedly. This is the existing behavior
and is harmless. If this becomes a concern, the flush Routine could be started only when
simulator mode is detected (e.g. on receipt of the first `/pad/` message), but that is
out of scope for this fix.
