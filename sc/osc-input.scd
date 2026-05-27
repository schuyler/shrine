// --- Simulator format handlers ---
// Pad numbers are 1-indexed in the simulator protocol.
4.do({ |i|
    var padNum = i + 1;
    OSCdef(("simCap" ++ padNum).asSymbol, { |msg|
        ~buses[\cap][i].set(msg[1]);
    }, "/pad/" ++ padNum ++ "/cap");
});

~config[\gsrPairs].do({ |pair, idx|
    var i = pair[0], j = pair[1];

    OSCdef(("simGsrMag" ++ i ++ "_" ++ j).asSymbol, { |msg|
        s.sendMsg(\c_set, ~buses[\gsrMag].index + idx, msg[1]);
    }, "/gsr/" ++ i ++ "/" ++ j);

    OSCdef(("simGsrPhase" ++ i ++ "_" ++ j).asSymbol, { |msg|
        // Simulator already sends 0..2pi; store as-is.
        s.sendMsg(\c_set, ~buses[\gsrPhase].index + idx, msg[1]);
    }, "/gsr/" ++ i ++ "/" ++ j ++ "/phase");
});

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

        // msg[1] = self_cap_mag
        ~buses[\cap][nodeId].set(msg[1]);

        // msg[2..4] = gsr_mag[0..2], msg[5..7] = gsr_phase[0..2]
        mapping.do({ |globalIdx, localIdx|
            if(globalIdx.notNil, {
                var rawPhase = msg[5 + localIdx];
                // Normalize -pi..pi → 0..2pi
                var normPhase = if(rawPhase < 0, { rawPhase + (2 * pi) }, { rawPhase });
                s.sendMsg(\c_set, ~buses[\gsrMag].index + globalIdx, msg[2 + localIdx]);
                s.sendMsg(\c_set, ~buses[\gsrPhase].index + globalIdx, normPhase);
            });
        });
    }, "/shrine/node/" ++ nodeId);
});

"OSC handlers registered.".postln;
