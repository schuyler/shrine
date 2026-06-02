// Accumulator arrays for simulator flush
~simAccum = IdentityDictionary.new;
~simAccum[\cap]      = 4.collect({ 0.0 });
~simAccum[\gsrMag]   = 6.collect({ 0.0 });

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
});

// 30 Hz flush routine: sends one bundle containing two \c_setn commands.
// Stored in ~simFlushRoutine so it can be stopped cleanly.
// Stop any previous instance (safe for REPL re-execution).
if(~simFlushRoutine.notNil, { ~simFlushRoutine.stop });

~simFlushRoutine = Routine({
    loop({
        var capSnap      = ~simAccum[\cap].copy;
        var gsrMagSnap   = ~simAccum[\gsrMag].copy;
        s.sendBundle(nil,
            [\c_setn, ~buses[\cap].index,      4, *capSnap],
            [\c_setn, ~buses[\gsrMag].index,   6, *gsrMagSnap]
        );
        (1/30).wait;
    });
}).play(SystemClock);  // SystemClock intentionally — not inherited from enclosing AppClock Routine

// --- Edge node format handlers ---
// /shrine/node/N sends 5 floats:
//   msg[1] = self_stdev (used as cap value)
//   msg[2] = self_carrier_mag (parsed but not routed — no current consumer)
//   msg[3..5] = gsr_mag[0..2]
4.do({ |nodeId|
    OSCdef(("edgeNode" ++ nodeId).asSymbol, { |msg|
        var mapping = ~config[\nodeGsrMapping][nodeId];
        var bundle = Array.new;

        // msg[1] = self_stdev → cap bus
        bundle = bundle.add([\c_set, ~buses[\cap].index + nodeId, msg[1]]);

        // msg[3..5] = gsr_mag[0..2] → mapped to global pair indices
        mapping.do({ |globalIdx, localIdx|
            bundle = bundle.add([\c_set, ~buses[\gsrMag].index + globalIdx, msg[3 + localIdx]]);
        });

        s.sendBundle(nil, *bundle);
    }, "/shrine/node/" ++ nodeId);
});

"OSC handlers registered.".postln;
