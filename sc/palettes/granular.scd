// Granular palette for Shrine / MiniCAT
//
// \pad_voice — one per pad. GrainBuf granular synthesis driven by capacitive touch.
//   - Touch (cap) controls: grain density, duration, filter cutoff, amplitude, buffer scan speed
//   - GSR (average of 3 neighbors) introduces subtle pitch drift
//   - No touch = silence. Full touch = dense, bright grains.
//
// \pair_voice — driven by 1 GSR pair. Additive sine cluster, 2 harmonics max.
//   - GSR magnitude controls base frequency and amplitude
//   - Coherence fixed at 1.0 (single pair, no meaningful inter-signal comparison)
//
// \triad_voice — driven by 3 GSR pairs. Additive sine cluster, 3 harmonics max.
//   - GSR magnitude mean controls base frequency and amplitude
//   - Count of active GSR connections controls harmonic richness
//   - GSR magnitude-variance coherence controls filter brightness

SynthDef(\pad_voice, {
    arg out = 0, capBus, gsrBus1, gsrBus2, gsrBus3,
        bufnum, gate = 1, amp = 0.3,
        trigRateMin = 1, trigRateMax = 40,
        grainDurIdle = 0.3, grainDurFull = 0.05,
        filterLo = 300, filterHi = 8000, filterRq = 0.7,
        gsrDrift = 0.1,
        posSpeedMin = 0.1, posSpeedMax = 2;

    var cap = In.kr(capBus);        // 0.0-1.0
    var gsr1 = In.kr(gsrBus1);
    var gsr2 = In.kr(gsrBus2);
    var gsr3 = In.kr(gsrBus3);

    // --- Grain parameters mapped from cap ---

    // Grain trigger rate: 1-40 Hz, exponential mapping for perceptual evenness
    var trigRate = cap.linexp(0, 1, trigRateMin, trigRateMax);
    var trig = Impulse.ar(trigRate);

    // Grain duration: idle=0.3s (spacious), full=0.05s (dense)
    var grainDur = cap.linlin(0, 1, grainDurIdle, grainDurFull);

    // Playback rate: centered at 1.0, GSR introduces slight pitch drift
    var gsrSum = (gsr1 + gsr2 + gsr3) / 3;
    var rate = 1.0 + (gsrSum * LFNoise1.kr(0.5).range(gsrDrift.neg, gsrDrift));

    // Buffer position: slow random walk, speed increases with touch
    var posSpeed = cap.linlin(0, 1, posSpeedMin, posSpeedMax);
    var pos = LFNoise1.kr(posSpeed).range(0, 1);

    // Amplitude envelope: cap controls overall level
    // Square-root mapping so quiet touches are still audible
    var grainAmp = cap.sqrt * amp;

    // GrainBuf with numChannels: 1 produces mono
    var sig = GrainBuf.ar(
        numChannels: 1,
        trigger: trig,
        dur: grainDur,
        sndbuf: bufnum,
        rate: rate,
        pos: pos,
        interp: 2        // linear interpolation
    );

    // Filter cutoff mapped from cap — low touch = dark, full touch = bright
    var filtered = RLPF.ar(sig, cap.linexp(0, 1, filterLo, filterHi), filterRq);

    // Gate envelope for clean startup/shutdown
    var env = EnvGen.kr(Env.asr(0.1, 1, 0.5), gate, doneAction: 2);

    Out.ar(out, filtered * grainAmp * env);
}).add;

SynthDef(\pair_voice, {
    arg out1, out2, gsrMagBus, amp = 0.03,
        baseFreqMin = 40, baseFreqMax = 120,
        collFilterLo = 200, collFilterHi = 4000,
        gsrActiveThreshold = 0.1;

    // Single GSR pair: magnitude only (FDM — no phase)
    var activity = In.kr(gsrMagBus);   // 0-1

    // 0 or 1 — UGen-level comparison, not language-level .if()
    var activeCount = (activity > gsrActiveThreshold);

    // Single pair gives no meaningful inter-signal comparison; fix coherence fully on
    var coherence = 1.0;

    // Base frequency driven by activity
    var baseFreq = activity.linexp(0, 1, baseFreqMin, baseFreqMax);

    // 1 harmonic when inactive, 2 when active
    var numHarmonics = activeCount.linlin(0, 1, 1, 2).round;

    // Additive sine cluster, 2 harmonics max.
    // Lag.kr smooths the on/off transition over 100ms, preventing clicks.
    // (i < numHarmonics) is a BinaryOpUGen — do NOT use .if() here.
    var sig = Mix.fill(2, { |i|
        var harmonicAmp = Lag.kr((i < numHarmonics) * 1, 0.1);
        var freq = baseFreq * (i + 1) * (1 + (LFNoise1.kr(0.3).range(-0.005, 0.005)));
        SinOsc.ar(freq) * harmonicAmp / (i + 1)
    });

    var level = activity.sqrt * amp;

    // coherence is fixed at 1.0, so filter always uses collFilterHi
    var filtered = LPF.ar(sig, coherence.linexp(0, 1, collFilterLo, collFilterHi));

    Out.ar(out1, filtered * level);
    Out.ar(out2, filtered * level);
}).add;

SynthDef(\triad_voice, {
    arg out1, out2, out3,
        gsrMagBus1, gsrMagBus2, gsrMagBus3,
        amp = 0.02,
        baseFreqMin = 40, baseFreqMax = 120,
        collFilterLo = 200, collFilterHi = 4000,
        gsrActiveThreshold = 0.1;

    // Read 3 magnitudes individually (buses may not be consecutive)
    var mag1 = In.kr(gsrMagBus1);
    var mag2 = In.kr(gsrMagBus2);
    var mag3 = In.kr(gsrMagBus3);

    // Overall GSR activity: mean of 3 magnitudes
    var activity = (mag1 + mag2 + mag3) / 3;

    // Count of "active" connections (magnitude > threshold)
    var activeCount = (mag1 > gsrActiveThreshold) + (mag2 > gsrActiveThreshold) + (mag3 > gsrActiveThreshold);

    // Magnitude-variance coherence: low variance = high coherence = more tonal / brighter
    // When all 3 magnitudes are similar, coherence is high (uniform engagement).
    // When magnitudes diverge, coherence drops (uneven engagement).
    var magMean = (mag1 + mag2 + mag3) / 3;
    var magVar = ((mag1 - magMean).squared + (mag2 - magMean).squared + (mag3 - magMean).squared) / 3;
    var coherence = magVar.linlin(0, 0.1, 1, 0).clip(0, 1);

    // Base frequency driven by activity
    var baseFreq = activity.linexp(0, 1, baseFreqMin, baseFreqMax);

    // 1–3 harmonics mapped from active connection count
    var numHarmonics = activeCount.linlin(0, 3, 1, 3).round;

    // Additive sine cluster, 3 harmonics max.
    // Lag.kr smooths on/off transitions over 100ms.
    // (i < numHarmonics) is a BinaryOpUGen — do NOT use .if() here.
    var sig = Mix.fill(3, { |i|
        var harmonicAmp = Lag.kr((i < numHarmonics) * 1, 0.1);
        var freq = baseFreq * (i + 1) * (1 + (LFNoise1.kr(0.3).range(-0.005, 0.005)));
        SinOsc.ar(freq) * harmonicAmp / (i + 1)
    });

    var level = activity.sqrt * amp;

    // Coherence controls filter brightness
    var filtered = LPF.ar(sig, coherence.linexp(0, 1, collFilterLo, collFilterHi));

    Out.ar(out1, filtered * level);
    Out.ar(out2, filtered * level);
    Out.ar(out3, filtered * level);
}).add;

"Granular palette loaded (\\pad_voice, \\pair_voice, \\triad_voice).".postln;
