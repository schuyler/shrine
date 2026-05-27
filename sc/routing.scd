// IMPORTANT: This file must be executed from within a Routine
// (as done by startup.scd). s.sync calls have no effect outside a Routine.

// --- Groups for execution order ---
~groups = IdentityDictionary.new;
~groups[\sources] = Group.new(s, \addToHead);
~groups[\effects] = Group.after(~groups[\sources]);

// --- Load sample buffers ---
~buffers = 4.collect({ |i|
    var path = PathName(thisProcess.nowExecutingPath).pathOnly
        +/+ "samples" +/+ "pad" ++ (i + 1) ++ ".wav";
    Buffer.read(s, path);
});
s.sync;  // wait for buffers to load

// Populate client-side buffer metadata (numFrames etc.) from the server.
// Without this, buf.numFrames is always 0 regardless of load success.
~buffers.do({ |buf| buf.query });
s.sync;

// Check for missing buffers
~buffers.do({ |buf, i|
    if(buf.numFrames == 0, {
        ("WARNING: pad" ++ (i+1) ++ ".wav failed to load or is empty").postln;
    });
});

// --- GSR bus assignments per pad ---
// Which 3 GSR pair indices are relevant to each pad?
// Pad 0 participates in pairs: (0,1)=0, (0,2)=1, (0,3)=2
// Pad 1 participates in pairs: (0,1)=0, (1,2)=3, (1,3)=4
// Pad 2 participates in pairs: (0,2)=1, (1,2)=3, (2,3)=5
// Pad 3 participates in pairs: (0,3)=2, (1,3)=4, (2,3)=5
~config[\padGsrIndices] = [
    [0, 1, 2],  // pad 0
    [0, 3, 4],  // pad 1
    [1, 3, 5],  // pad 2
    [2, 4, 5],  // pad 3
];

// --- Instantiate pad voices ---
~synths = IdentityDictionary.new;
~synths[\padVoices] = 4.collect({ |i|
    var gsrIdx = ~config[\padGsrIndices][i];
    Synth(\pad_voice, [
        \out, ~buses[\padAudio][i].index,
        \capBus, ~buses[\cap].index + i,
        \gsrBus1, ~buses[\gsrMag].index + gsrIdx[0],
        \gsrBus2, ~buses[\gsrMag].index + gsrIdx[1],
        \gsrBus3, ~buses[\gsrMag].index + gsrIdx[2],
        \bufnum, ~buffers[i].bufnum,
    ], ~groups[\sources]);
});

// --- Instantiate pair voices ---
// One per GSR pair. Each writes to both pads' collective audio buses.
~config[\padPairs] = [[0,1],[0,2],[0,3],[1,2],[1,3],[2,3]];
~synths[\pairVoices] = ~config[\padPairs].collect({ |pair, gsrIdx|
    Synth(\pair_voice, [
        \out1, ~buses[\collectiveAudio][pair[0]].index,
        \out2, ~buses[\collectiveAudio][pair[1]].index,
        \gsrMagBus, ~buses[\gsrMag].index + gsrIdx,
    ], ~groups[\sources]);
});

// --- Instantiate triad voices ---
// One per triad of pads. Each writes to all three pads' collective audio buses.
~config[\padTriads] = [[0,1,2],[0,1,3],[0,2,3],[1,2,3]];
~config[\triadGsrIndices] = [[0,1,3],[0,2,4],[1,2,5],[3,4,5]];
~synths[\triadVoices] = ~config[\padTriads].collect({ |triad, idx|
    var gsrIdx = ~config[\triadGsrIndices][idx];
    Synth(\triad_voice, [
        \out1, ~buses[\collectiveAudio][triad[0]].index,
        \out2, ~buses[\collectiveAudio][triad[1]].index,
        \out3, ~buses[\collectiveAudio][triad[2]].index,
        \gsrMagBus1, ~buses[\gsrMag].index + gsrIdx[0],
        \gsrMagBus2, ~buses[\gsrMag].index + gsrIdx[1],
        \gsrMagBus3, ~buses[\gsrMag].index + gsrIdx[2],
        \gsrPhaseBus1, ~buses[\gsrPhase].index + gsrIdx[0],
        \gsrPhaseBus2, ~buses[\gsrPhase].index + gsrIdx[1],
        \gsrPhaseBus3, ~buses[\gsrPhase].index + gsrIdx[2],
    ], ~groups[\sources]);
});

// --- Output mixer SynthDef (infrastructure, not palette) ---
SynthDef(\output_mixer, {
    arg padIn, collectiveIn, out = 0,
        gsrMagBuses,
        reverbRoom = 0.7, amp = 1.0,
        collMixMin = 0.1, collMixMax = 0.6,
        revMixMin = 0.05, revMixMax = 0.4,
        reverbDamp = 0.5;

    var pad = In.ar(padIn);
    var coll = In.ar(collectiveIn);

    // Average GSR magnitude across all 6 pairs (0.0-1.0)
    var avgGsr = In.kr(gsrMagBuses, 6).mean;

    // GSR drives collective mix: low GSR = mostly pad, high GSR = blend
    var collectiveMix = avgGsr.linlin(0, 1, collMixMin, collMixMax);

    // GSR also drives reverb send: more collective activity = more space
    var reverbMix = avgGsr.linlin(0, 1, revMixMin, revMixMax);

    // Mix pad voice with collective
    var mixed = pad + (coll * collectiveMix);

    // Simple reverb (FreeVerb is built-in, no sc3-plugins needed)
    var reverbed = FreeVerb.ar(mixed, reverbMix, reverbRoom, reverbDamp);

    // Soft limiter to prevent clipping
    var limited = reverbed.tanh;

    Out.ar(out, limited * amp);
}).add;
s.sync;

// --- Instantiate output mixers ---
~synths[\outputMixers] = 4.collect({ |i|
    Synth(\output_mixer, [
        \padIn, ~buses[\padAudio][i].index,
        \collectiveIn, ~buses[\collectiveAudio][i].index,
        \out, i,  // hardware output channel 0-3
        \gsrMagBuses, ~buses[\gsrMag].index,
    ], ~groups[\effects]);
});

// --- Stereo downmix (for 2-channel hardware) ---
// Sums channels 2-3 into channels 0-1 so all four pad voices are
// audible on stereo speakers. Harmless on 4-channel hardware.
SynthDef(\stereo_downmix, {
    Out.ar(0, In.ar(2, 2));  // additively mix ch2→ch0 and ch3→ch1
}).add;
s.sync;
~synths[\downmix] = Synth(\stereo_downmix, target: ~groups[\effects], addAction: \addToTail);

"Routing complete. 4 pad voices + 6 pair voices + 4 triad voices + 4 output mixers.".postln;
