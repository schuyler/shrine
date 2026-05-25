// Granular palette for Shrine / MiniCAT
//
// \pad_voice — one per pad. GrainBuf granular synthesis driven by capacitive touch.
//   - Touch (cap) controls: grain density, duration, filter cutoff, amplitude, buffer scan speed
//   - GSR (average of 3 neighbors) introduces subtle pitch drift
//   - No touch = silence. Full touch = dense, bright grains.
//
// \collective_voice — one total. Additive sine cluster driven by collective GSR state.
//   - GSR magnitude mean controls base frequency and amplitude
//   - Count of active GSR connections controls harmonic richness
//   - GSR phase coherence controls filter brightness

SynthDef(\pad_voice, {
    arg out = 0, capBus, gsrBus1, gsrBus2, gsrBus3,
        bufnum, gate = 1, amp = 0.3;

    var cap = In.kr(capBus);        // 0.0-1.0
    var gsr1 = In.kr(gsrBus1);
    var gsr2 = In.kr(gsrBus2);
    var gsr3 = In.kr(gsrBus3);

    // --- Grain parameters mapped from cap ---

    // Grain trigger rate: 1-40 Hz, exponential mapping for perceptual evenness
    var trigRate = cap.linexp(0, 1, 1, 40);
    var trig = Impulse.ar(trigRate);

    // Grain duration: 0.05-0.3 seconds (longer grains at low touch for spaciousness)
    var grainDur = cap.linlin(0, 1, 0.3, 0.05);

    // Playback rate: centered at 1.0, GSR introduces slight pitch drift
    var gsrSum = (gsr1 + gsr2 + gsr3) / 3;
    var rate = 1.0 + (gsrSum * LFNoise1.kr(0.5).range(-0.1, 0.1));

    // Buffer position: slow random walk, speed increases with touch
    var posSpeed = cap.linlin(0, 1, 0.1, 2);
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
    var filtered = RLPF.ar(sig, cap.linexp(0, 1, 300, 8000), 0.7);

    // Gate envelope for clean startup/shutdown
    var env = EnvGen.kr(Env.asr(0.1, 1, 0.5), gate, doneAction: 2);

    Out.ar(out, filtered * grainAmp * env);
}).add;

SynthDef(\collective_voice, {
    arg out = 0, gsrMagBuses, gsrPhaseBuses, amp = 0.15;

    var mags = In.kr(gsrMagBuses, 6);     // 6 GSR magnitudes
    var phases = In.kr(gsrPhaseBuses, 6);  // 6 GSR phases

    // Overall GSR activity: mean of all 6 magnitudes
    var activity = mags.mean;

    // Count of "active" connections (magnitude > 0.1)
    var activeCount = (mags > 0.1).sum;

    // Phase coherence: how similar are the phases?
    // Low variance = high coherence = more tonal result
    var phaseMean = phases.mean;
    var phaseVar = ((phases - phaseMean).squared).mean;
    var coherence = phaseVar.linlin(0, 2, 1, 0).clip(0, 1);

    // Base frequency: low drone, modulated by activity
    var baseFreq = activity.linexp(0, 1, 40, 120);

    // Harmonic richness: more active connections = more harmonics
    var numHarmonics = activeCount.linlin(0, 6, 1, 6).round;

    // Build additive sine cluster.
    // Lag.kr smooths the on/off transition of each harmonic over 100ms,
    // preventing clicks when numHarmonics crosses an integer boundary.
    var sig = Mix.fill(6, { |i|
        // (i < numHarmonics) produces a BinaryOpUGen that outputs 1.0 or 0.0.
        // Do NOT use .if() here — that's language-level, not UGen-level.
        var harmonicAmp = Lag.kr((i < numHarmonics) * 1, 0.1);
        var freq = baseFreq * (i + 1) * (1 + (LFNoise1.kr(0.3).range(-0.005, 0.005)));
        SinOsc.ar(freq) * harmonicAmp / (i + 1)
    });

    // Apply amplitude: activity controls overall level
    var level = activity.sqrt * amp;

    // Coherence controls filter brightness
    var filtered = LPF.ar(sig, coherence.linexp(0, 1, 200, 4000));

    Out.ar(out, filtered * level);
}).add;

"Granular palette loaded (\\pad_voice, \\collective_voice).".postln;
