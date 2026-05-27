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

// 30 Hz flush routine: sends one bundle containing three \c_setn commands.
// Stored in ~simFlushRoutine so it can be stopped cleanly.
// Stop any previous instance (safe for REPL re-execution).
if(~simFlushRoutine.notNil, { ~simFlushRoutine.stop });

~simFlushRoutine = Routine({
    loop({
        var capSnap      = ~simAccum[\cap].copy;
        var gsrMagSnap   = ~simAccum[\gsrMag].copy;
        var gsrPhaseSnap = ~simAccum[\gsrPhase].copy;
        s.sendBundle(nil,
            [\c_setn, ~buses[\cap].index,      4, *capSnap],
            [\c_setn, ~buses[\gsrMag].index,   6, *gsrMagSnap],
            [\c_setn, ~buses[\gsrPhase].index, 6, *gsrPhaseSnap]
        );
        (1/30).wait;
    });
}).play(SystemClock);  // SystemClock intentionally — not inherited from enclosing AppClock Routine

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
                // Normalize -pi..pi → 0..2pi
                var normPhase = if(rawPhase < 0, { rawPhase + (2 * pi) }, { rawPhase });
                bundle = bundle.add([\c_set, ~buses[\gsrMag].index + globalIdx, msg[2 + localIdx]]);
                bundle = bundle.add([\c_set, ~buses[\gsrPhase].index + globalIdx, normPhase]);
            });
        });

        s.sendBundle(nil, *bundle);
    }, "/shrine/node/" ++ nodeId);
});

"OSC handlers registered.".postln;
