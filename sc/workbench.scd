// Shrine — Sound Design Workbench
//
// Standalone texture explorer. Does NOT depend on startup.scd, buses.scd,
// osc-input.scd, or any other Shrine engine file. Boots its own server
// and is fully self-contained.
//
// HOW TO USE:
//   1. Open this file in the SuperCollider IDE.
//   2. Select all (Cmd-A) and evaluate (Shift-Enter or Cmd-Return).
//   3. Wait for the GUI window to appear — the server boot takes a moment.
//   4. Pick a source (Sample / Granular / Oscillator / Noise).
//   5. Adjust effect stages with their bypass toggles and sliders.
//   6. Use "Load Sample" to replace the default sample (sc/samples/pad1.wav).
//   7. (Optional) For Freesound search: install the Freesound quark
//      (Quarks.install("Freesound")) and set FREESOUND_API_TOKEN env var.
//
// SIGNAL CHAIN:
//   Ndef(\source) → Ndef(\fx_filter) → Ndef(\fx_chorus)
//                → Ndef(\fx_phaser) → Ndef(\fx_reverb) → hardware out
//
// Each effect Ndef reads Ndef(\previous).ar directly.
// Bypass (1 = pass-through, 0 = active) uses Select.ar so switching is
// click-free and no rebuilding of the Ndef graph is required.
(
// ------------------------------------------------------------------
// All var declarations must precede executable code in SC.
// ------------------------------------------------------------------
var s, buf, samplePath, w;
var srcButtons;

// State variables (language-side; Ndefs read via .set)
var sourceMode    = 0;     // 0=Sample, 1=Granular, 2=Oscillator, 3=Noise

// Sample / Granular
var sampleRate    = 1.0;
var sampleLoop    = 1;
var grainDensity  = 10.0;
var grainDur      = 0.1;
var grainPosSpeed = 0.5;
var grainPitch    = 1.0;

// Oscillator
var oscWave       = 0;     // 0=sine, 1=saw, 2=square, 3=tri
var oscFreq       = 220.0;
var oscVibRate    = 5.0;
var oscVibDepth   = 0.0;

// Noise
var noiseType     = 0;     // 0=white, 1=pink, 2=brown

// Filter
var fxFilterBypass  = 1;
var filterType      = 0;   // 0=LP, 1=HP, 2=BP
var filterCutoff    = 1000.0;
var filterRq        = 0.7;

// Chorus
var fxChorusBypass  = 1;
var chorusRate      = 1.0;
var chorusDepth     = 3.0;
var chorusMix       = 0.5;

// Phaser
var fxPhaserBypass  = 1;
var phaserRate      = 0.5;
var phaserFeedback  = 0.6;
var phaserMix       = 0.5;

// Reverb
var fxReverbBypass  = 1;
var reverbDecay     = 3.0;
var reverbDamp      = 0.5;
var reverbMix       = 0.4;

// Output
var masterAmp     = 0.4;

// Freesound integration
var freesoundAvailable = false;
var freesoundToken;
var freesoundDir;
var freesoundWin;

// Helpers
var colWidth = 520;

var sectionLabel = { |parent, text|
    var lbl = StaticText(parent, Rect(0, 0, colWidth, 22));
    lbl.string = text;
    lbl.font = Font.default.copy.bold_(true).size_(13);
    lbl.stringColor = Color.white;
    lbl;
};

var makeSlider = { |parent, label, spec, initVal, action|
    var ez = EZSlider(parent, colWidth@26, label, spec, action, initVal,
        unitWidth: 0, labelWidth: 150);
    ez.labelView.stringColor = Color.white;
    ez.numberView.stringColor = Color.white;
    ez.numberView.normalColor = Color.white;
    ez.numberView.typingColor = Color.cyan;
    ez.numberView.background = Color.gray(0.25);
    ez;
};

var makeBypassButton = { |parent, label, initBypass, action|
    // States: [bypassed (grey), active (green)]
    var btn = Button(parent, 120@26)
        .states_([
            [label ++ " [bypass]", Color.black, Color.gray(0.6)],
            [label ++ " [ON]",     Color.black, Color(0.2, 0.8, 0.3)]
        ])
        .value_(if(initBypass == 1, { 0 }, { 1 }))
        .action_(action);
    btn;
};

var openFreesoundSearch = {
    // Singleton — bring to front if already open
    if(freesoundWin.notNil and: { freesoundWin.isClosed.not }, {
        freesoundWin.front;
    }, {
        var searchField, goBtn, resultsList, statusText, loadBtn;
        var prevBtn, nextBtn;
        var minDurBox, maxDurBox;
        var currentPager, currentSounds;
        var populateResults;
        var freesoundLoading = false;

        freesoundWin = Window("Freesound Search", Rect(100, 100, 400, 520));
        freesoundWin.view.background = Color.gray(0.15);
        freesoundWin.view.addFlowLayout(8@8, 6@6);

        // Search row
        StaticText(freesoundWin.view, 55@24)
            .string_("Search:")
            .stringColor_(Color.white);
        searchField = TextField(freesoundWin.view, 240@24)
            .background_(Color.gray(0.25))
            .stringColor_(Color.white);
        goBtn = Button(freesoundWin.view, 60@24)
            .states_([["Go", Color.black, Color.gray(0.7)]]);

        // Duration filter row
        freesoundWin.view.decorator.nextLine;
        StaticText(freesoundWin.view, 60@24)
            .string_("Duration:")
            .stringColor_(Color.white);
        minDurBox = NumberBox(freesoundWin.view, 50@24)
            .value_(1)
            .background_(Color.gray(0.25))
            .normalColor_(Color.white)
            .typingColor_(Color.cyan);
        StaticText(freesoundWin.view, 20@24)
            .string_("to")
            .stringColor_(Color.white);
        maxDurBox = NumberBox(freesoundWin.view, 50@24)
            .value_(10)
            .background_(Color.gray(0.25))
            .normalColor_(Color.white)
            .typingColor_(Color.cyan);
        StaticText(freesoundWin.view, 30@24)
            .string_("sec")
            .stringColor_(Color.white);

        // Results list
        freesoundWin.view.decorator.nextLine;
        resultsList = ListView(freesoundWin.view, 380@280)
            .background_(Color.gray(0.2))
            .stringColor_(Color.white)
            .selectedStringColor_(Color.black)
            .hiliteColor_(Color(0.3, 0.7, 1.0))
            .items_(["(no results)"]);

        // Status text
        freesoundWin.view.decorator.nextLine;
        statusText = StaticText(freesoundWin.view, 380@20)
            .string_("")
            .stringColor_(Color.gray(0.7));

        // Navigation row
        freesoundWin.view.decorator.nextLine;
        prevBtn = Button(freesoundWin.view, 70@26)
            .states_([["<< Prev", Color.white, Color.gray(0.35)]]);
        nextBtn = Button(freesoundWin.view, 70@26)
            .states_([["Next >>", Color.white, Color.gray(0.35)]]);
        // Spacer
        StaticText(freesoundWin.view, 90@26).string_("");
        loadBtn = Button(freesoundWin.view, 140@26)
            .states_([
                ["Load into Workbench", Color.white, Color(0.1, 0.3, 0.8)],
                ["Downloading...",      Color.gray(0.5), Color.gray(0.35)]
            ]);

        // Helper: populate resultsList from a pager
        populateResults = { |pager|
            var items = [];
            var sounds = [];
            pager.do { |snd, i|
                items = items.add(
                    "%: % (%.1fs) — %".format(
                        i + 1,
                        snd["name"],
                        snd["duration"],
                        snd["username"]
                    )
                );
                sounds = sounds.add(snd);
            };
            currentPager = pager;
            currentSounds = sounds;
            {
                if(items.size > 0, {
                    resultsList.items_(items);
                }, {
                    resultsList.items_(["(no results)"]);
                });
                prevBtn.enabled_(pager.dict["prev"].notNil);
                nextBtn.enabled_(pager.dict["next"].notNil);
                statusText.string_(
                    "% result(s) — use Prev/Next to page".format(items.size)
                );
            }.defer;
        };

        // Go button action
        goBtn.action_({
            var query  = searchField.string.stripWhiteSpace;
            var minDur = minDurBox.value;
            var maxDur = maxDurBox.value;
            var filter = "duration:[% TO %]".format(minDur.asInteger, maxDur.asInteger);
            if(query.size > 0, {
                { statusText.string_("Searching...") }.defer;
                FSSound.textSearch(
                    query:  query,
                    filter: filter,
                    sort:   nil,
                    params: IdentityDictionary["fields" -> "id,name,tags,username,license,previews,duration"],
                    action: { |pager|
                        populateResults.(pager);
                    }
                );
            }, {
                { statusText.string_("Enter a search term.") }.defer;
            });
        });

        // Allow Enter key in search field to trigger Go
        searchField.action_({ goBtn.doAction });

        // Prev/Next
        prevBtn.action_({
            if(currentPager.notNil, {
                { statusText.string_("Loading previous page...") }.defer;
                currentPager.prev { |newPager| populateResults.(newPager) };
            });
        });

        nextBtn.action_({
            if(currentPager.notNil, {
                { statusText.string_("Loading next page...") }.defer;
                currentPager.next { |newPager| populateResults.(newPager) };
            });
        });

        // Load button action
        loadBtn.action_({
            var idx = resultsList.value;
            if(freesoundLoading.not and: {
                currentSounds.notNil and: {
                    idx.notNil and: { idx < currentSounds.size }
                }
            }, {
                var snd = currentSounds[idx];
                freesoundLoading = true;
                { loadBtn.value_(1) }.defer;
                File.mkdir(freesoundDir);
                try {
                    snd.retrievePreview(
                        freesoundDir ++ "/",
                        { |exitCode|
                            Routine({
                                try {
                                    var filePath = freesoundDir +/+ snd.previewFilename("mp3");
                                    var newBuf;
                                    if(exitCode == 0, {
                                        newBuf = Buffer.read(s, filePath);
                                        s.sync;
                                        newBuf.query;
                                        s.sync;
                                        if(newBuf.numFrames == 0, {
                                            ("WARNING: Freesound preview loaded 0 frames: " ++ filePath).postln;
                                            { statusText.string_("Load failed (0 frames).") }.defer;
                                        }, {
                                            buf.free;
                                            buf = newBuf;
                                            Ndef(\source).set(\bufnum, buf.bufnum);
                                            if(sourceMode > 1, {
                                                sourceMode = 0;
                                                Ndef(\source).set(\mode, 0);
                                                { srcButtons.do { |b, j|
                                                    b.value_(if(j == 0, { 1 }, { 0 }))
                                                } }.defer;
                                            });
                                            { statusText.string_(
                                                "Loaded: %".format(snd["name"])
                                            ) }.defer;
                                        });
                                    }, {
                                        ("WARNING: retrievePreview failed, exit code: " ++ exitCode).postln;
                                        { statusText.string_(
                                            "Download failed (exit %).".format(exitCode)
                                        ) }.defer;
                                    });
                                } { |err|
                                    err.reportError;
                                    { statusText.string_("Error: " ++ err.errorString) }.defer;
                                };
                                freesoundLoading = false;
                                { loadBtn.value_(0) }.defer;
                            }).play(AppClock);
                        },
                        "hq",
                        "mp3"
                    );
                } { |err|
                    err.reportError;
                    freesoundLoading = false;
                    { loadBtn.value_(0) }.defer;
                    { statusText.string_("Error launching download.") }.defer;
                };
            });
        });

        freesoundWin.front;
    });
};

// ------------------------------------------------------------------
// Server setup
// ------------------------------------------------------------------
s = Server.default;
s.options.numOutputBusChannels = 2;
s.options.numInputBusChannels  = 0;
s.options.sampleRate = 48000;
s.options.hardwareBufferSize = 1024;
// scsynth 3.14 queries the input device even with 0 input channels,
// crashing on Bluetooth devices with mismatched input/output sample rates.
// Workaround: create an Aggregate Device in Audio MIDI Setup combining
// the Bluetooth output with the built-in mic, both at 48kHz.
s.options.device_("SuperCollider");

// ------------------------------------------------------------------
// Boot sequence
// ------------------------------------------------------------------
s.waitForBoot({
    Routine({
        var base = PathName(thisProcess.nowExecutingPath).pathOnly;
        samplePath = base +/+ "samples" +/+ "pad1.wav";
        buf = Buffer.read(s, samplePath);
        s.sync;
        buf.query;
        s.sync;

        if(buf.numFrames == 0, {
            "WARNING: Default sample failed to load: %".format(samplePath).postln;
        }, {
            "Loaded sample: % (% frames, % Hz)".format(
                samplePath, buf.numFrames, buf.sampleRate).postln;
        });

        // Freesound integration (optional — requires Freesound quark)
        freesoundDir = base +/+ "samples" +/+ "freesound";
        freesoundToken = "FREESOUND_API_TOKEN".getenv;
        if(freesoundToken.notNil and: { freesoundToken.size > 0 }, {
            if(\Freesound.asClass.notNil, {
                Freesound.authType = "token";
                Freesound.token = freesoundToken;
                freesoundAvailable = true;
                "Freesound integration available.".postln;
            }, {
                "Freesound quark not installed. Run: Quarks.install(\"Freesound\")".postln;
            });
        }, {
            "FREESOUND_API_TOKEN not set — Freesound search disabled.".postln;
        });

        // ----------------------------------------------------------
        // Ndefs — fade time so source/fx changes don't click
        // ----------------------------------------------------------
        [\source, \fx_filter, \fx_chorus, \fx_phaser, \fx_reverb].do { |n|
            Ndef(n).fadeTime = 0.5;
        };

        // ----------------------------------------------------------
        // SOURCE Ndef
        // ----------------------------------------------------------
        Ndef(\source, {
            |mode=0,
             bufnum=0,
             sampleRate=1.0, sampleLoop=1,
             grainDensity=10.0, grainDur=0.1, grainPosSpeed=0.5, grainPitch=1.0,
             oscWave=0, oscFreq=220.0, oscVibRate=5.0, oscVibDepth=0.0,
             noiseType=0,
             amp=0.4|

            var pos, trig, grainSig, oscSig, noiseSig, sampleSig;
            var vibrato, oscBase;
            var sig;

            // --- Sample player (mono → stereo via ! 2) ---
            sampleSig = PlayBuf.ar(
                numChannels: 1,
                bufnum: bufnum,
                rate: BufRateScale.kr(bufnum) * sampleRate,
                loop: sampleLoop
            ) ! 2;

            // --- Granular (mono → stereo via ! 2) ---
            trig = Impulse.ar(grainDensity);
            pos  = LFNoise1.kr(grainPosSpeed).range(0, 1);
            grainSig = GrainBuf.ar(
                numChannels: 1,
                trigger: trig,
                dur: grainDur,
                sndbuf: bufnum,
                rate: grainPitch,
                pos: pos,
                interp: 2
            ) ! 2;

            // --- Oscillator (Select.ar over 4 wave types) ---
            vibrato = SinOsc.kr(oscVibRate) * oscVibDepth;
            oscBase = oscFreq + vibrato;
            oscSig = Select.ar(oscWave, [
                SinOsc.ar(oscBase),
                LFSaw.ar(oscBase),
                LFPulse.ar(oscBase),
                LFTri.ar(oscBase)
            ]);
            oscSig = oscSig ! 2;   // mono -> stereo

            // --- Noise (Select.ar over 3 noise types) ---
            noiseSig = Select.ar(noiseType, [
                WhiteNoise.ar ! 2,
                PinkNoise.ar ! 2,
                BrownNoise.ar ! 2
            ]);

            // --- Mode selection (Select.ar — no language-side branching) ---
            sig = Select.ar(mode, [sampleSig, grainSig, oscSig, noiseSig]);

            sig * amp;
        });

        Ndef(\source).set(
            \mode,         sourceMode,
            \bufnum,       buf.bufnum,
            \sampleRate,   sampleRate,
            \sampleLoop,   sampleLoop,
            \grainDensity, grainDensity,
            \grainDur,     grainDur,
            \grainPosSpeed,grainPosSpeed,
            \grainPitch,   grainPitch,
            \oscWave,      oscWave,
            \oscFreq,      oscFreq,
            \oscVibRate,   oscVibRate,
            \oscVibDepth,  oscVibDepth,
            \noiseType,    noiseType,
            \amp,          masterAmp
        );

        // ----------------------------------------------------------
        // FX: Filter
        // ----------------------------------------------------------
        Ndef(\fx_filter, {
            |bypass=1, filterType=0, cutoff=1000.0, rq=0.7|
            var dry = Ndef(\source).ar(2);
            var lp  = RLPF.ar(dry, cutoff, rq);
            var hp  = RHPF.ar(dry, cutoff, rq);
            var bp  = BPF.ar(dry, cutoff, rq);
            var processed = Select.ar(filterType, [lp, hp, bp]);
            // bypass=1 -> dry passthrough, bypass=0 -> processed
            Select.ar(bypass, [processed, dry]);
        });

        Ndef(\fx_filter).set(
            \bypass,     fxFilterBypass,
            \filterType, filterType,
            \cutoff,     filterCutoff,
            \rq,         filterRq
        );

        // ----------------------------------------------------------
        // FX: Chorus
        // ----------------------------------------------------------
        Ndef(\fx_chorus, {
            |bypass=1, rate=1.0, depth=3.0, mix=0.5|
            var dry = Ndef(\fx_filter).ar(2);
            var depthSec = depth * 0.001;
            var lfo = SinOsc.kr(rate, [0, 0.5pi]) * depthSec + (depthSec * 2);
            // Two detuned delay lines for stereo width
            var wet = DelayC.ar(dry, 0.1, lfo);
            var processed = (dry * (1 - mix)) + (wet * mix);
            Select.ar(bypass, [processed, dry]);
        });

        Ndef(\fx_chorus).set(
            \bypass, fxChorusBypass,
            \rate,   chorusRate,
            \depth,  chorusDepth,
            \mix,    chorusMix
        );

        // ----------------------------------------------------------
        // FX: Phaser (AllpassL cascade with LFO-swept delay + feedback)
        // ----------------------------------------------------------
        Ndef(\fx_phaser, {
            |bypass=1, rate=0.5, feedback=0.6, mix=0.5|
            var dry = Ndef(\fx_chorus).ar(2);
            var lfo = SinOsc.kr(rate).range(0.001, 0.02);
            var fb = LocalIn.ar(2);
            var wet = dry + (fb * feedback);
            var processed;
            // 6-stage allpass cascade with staggered LFO delay times
            6.do { |i|
                var delTime = lfo + (i * 0.002);
                wet = AllpassL.ar(wet, 0.025, delTime, 0.0);
            };
            LocalOut.ar(wet);
            processed = (dry * (1 - mix)) + (wet * mix);
            Select.ar(bypass, [processed, dry]);
        });

        Ndef(\fx_phaser).set(
            \bypass,   fxPhaserBypass,
            \rate,     phaserRate,
            \feedback, phaserFeedback,
            \mix,      phaserMix
        );

        // ----------------------------------------------------------
        // FX: Reverb
        // ----------------------------------------------------------
        Ndef(\fx_reverb, {
            |bypass=1, decay=3.0, damp=0.5, mix=0.4|
            var dry = Ndef(\fx_phaser).ar(2);
            var input = dry;
            var wet, lpf_freq, processed;
            // Pre-delay
            input = DelayN.ar(input, 0.05, 0.03);
            // Damping: map 0..1 to 10kHz..1kHz
            lpf_freq = damp.linexp(0, 1, 10000, 1000);
            // 4 parallel comb filters with prime-ratio delays
            wet = Mix.ar([
                CombL.ar(input, 0.1, 0.0297, decay),
                CombL.ar(input, 0.1, 0.0371, decay),
                CombL.ar(input, 0.1, 0.0411, decay),
                CombL.ar(input, 0.1, 0.0437, decay),
            ]);
            // Damping filter inside feedback path
            wet = LPF.ar(wet, lpf_freq);
            // 2 allpass diffusors
            wet = AllpassL.ar(wet, 0.05, 0.005, decay * 0.5);
            wet = AllpassL.ar(wet, 0.05, 0.017, decay * 0.5);
            // Normalize — 4 comb filters sum, so scale down
            wet = wet * 0.4;
            processed = (dry * (1 - mix)) + (wet * mix);
            Select.ar(bypass, [processed, dry]);
        });

        Ndef(\fx_reverb).set(
            \bypass, fxReverbBypass,
            \decay,  reverbDecay,
            \damp,   reverbDamp,
            \mix,    reverbMix
        );

        // Route reverb output to hardware
        Ndef(\fx_reverb).play(0, 2);

        "Workbench Ndefs initialized.".postln;

        // ----------------------------------------------------------
        // GUI
        // ----------------------------------------------------------
        {
            var leftCol, rightCol;
            var loadBtn;
            var loadingGuard = false;
            var pad = 10;

            srcButtons = Array.new(4);

            w = Window("Shrine Workbench", Rect(40, 40, (colWidth + pad) * 2 + pad, 660));
            w.view.background = Color.gray(0.15);

            // Two-column layout: sources on left, effects + output on right
            leftCol = View(w.view, Rect(pad, pad, colWidth, 620));
            leftCol.background = Color.gray(0.15);
            leftCol.addFlowLayout(0@0, 4@4);

            rightCol = View(w.view, Rect(colWidth + (pad * 2), pad, colWidth, 620));
            rightCol.background = Color.gray(0.15);
            rightCol.addFlowLayout(0@0, 4@4);

            // ======================================================
            // LEFT COLUMN: SOURCE
            // ======================================================
            sectionLabel.(leftCol, "SOURCE");

            // Radio-style row of 4 source buttons
            ["Sample", "Granular", "Oscillator", "Noise"].do { |label, i|
                var btn = Button(leftCol, 125@28)
                    .states_([
                        [label, Color.white, Color.gray(0.3)],
                        [label, Color.black, Color(0.3, 0.7, 1.0)]
                    ])
                    .value_(if(i == sourceMode, { 1 }, { 0 }))
                    .action_({ |b|
                        if(b.value == 1, {
                            srcButtons.do { |other, j|
                                if(j != i, { other.value_(0) });
                            };
                            sourceMode = i;
                            Ndef(\source).set(\mode, i);
                        }, {
                            b.value_(1);
                        });
                    });
                srcButtons.add(btn);
            };

            // "Load Sample" button
            leftCol.decorator.nextLine;
            loadBtn = Button(leftCol, 180@26)
                .states_([
                    ["Load Sample...", Color.black, Color.gray(0.7)],
                    ["Loading...",     Color.gray(0.5), Color.gray(0.4)]
                ])
                .action_({
                    if(loadingGuard.not, {
                        Dialog.openPanel({ |path|
                            loadingGuard = true;
                            { loadBtn.value_(1) }.defer;
                            Routine({
                                var newBuf = Buffer.read(s, path);
                                s.sync;
                                newBuf.query;
                                s.sync;
                                if(newBuf.numFrames == 0, {
                                    ("WARNING: Failed to load: " ++ path).postln;
                                }, {
                                    buf.free;
                                    buf = newBuf;
                                    Ndef(\source).set(\bufnum, buf.bufnum);
                                    ("Loaded: " ++ path).postln;
                                });
                                loadingGuard = false;
                                { loadBtn.value_(0) }.defer;
                            }).play(AppClock);
                        }, {
                            // cancelled — no-op
                        }, false);
                    });
                });

            if(freesoundAvailable, {
                Button(leftCol, 140@26)
                    .states_([["Freesound...", Color.black, Color(0.9, 0.6, 0.2)]])
                    .action_({ openFreesoundSearch.() });
            }, {
                Button(leftCol, 140@26)
                    .states_([["Freesound", Color.gray(0.5), Color.gray(0.3)]])
                    .enabled_(false);
            });

            // ---- Sample / Granular params ----
            leftCol.decorator.nextLine;
            StaticText(leftCol, colWidth@16).string_("  Sample / Granular")
                .stringColor_(Color.gray(0.6)).font_(Font.default.copy.italic_(true));

            makeSlider.(leftCol, "playback rate",
                ControlSpec(0.25, 4.0, \exp, 0, 1.0),
                sampleRate,
                { |ez| sampleRate = ez.value; Ndef(\source).set(\sampleRate, ez.value) });

            Button(leftCol, 120@26)
                .states_([
                    ["loop: OFF", Color.white, Color.gray(0.35)],
                    ["loop: ON",  Color.black, Color(0.3, 0.7, 1.0)]
                ])
                .value_(sampleLoop)
                .action_({ |b|
                    sampleLoop = b.value;
                    Ndef(\source).set(\sampleLoop, b.value);
                });

            leftCol.decorator.nextLine;
            makeSlider.(leftCol, "grain density (Hz)",
                ControlSpec(1.0, 60.0, \exp, 0, grainDensity),
                grainDensity,
                { |ez| grainDensity = ez.value; Ndef(\source).set(\grainDensity, ez.value) });

            makeSlider.(leftCol, "grain duration (s)",
                ControlSpec(0.01, 0.5, \exp, 0, grainDur),
                grainDur,
                { |ez| grainDur = ez.value; Ndef(\source).set(\grainDur, ez.value) });

            makeSlider.(leftCol, "grain pos speed",
                ControlSpec(0.1, 5.0, \exp, 0, grainPosSpeed),
                grainPosSpeed,
                { |ez| grainPosSpeed = ez.value; Ndef(\source).set(\grainPosSpeed, ez.value) });

            makeSlider.(leftCol, "grain pitch",
                ControlSpec(0.25, 4.0, \exp, 0, grainPitch),
                grainPitch,
                { |ez| grainPitch = ez.value; Ndef(\source).set(\grainPitch, ez.value) });

            // ---- Oscillator params ----
            leftCol.decorator.nextLine;
            StaticText(leftCol, colWidth@16).string_("  Oscillator")
                .stringColor_(Color.gray(0.6)).font_(Font.default.copy.italic_(true));

            StaticText(leftCol, 80@26).string_("waveform:")
                .stringColor_(Color.white);
            PopUpMenu(leftCol, 160@26)
                .items_(["Sine", "Saw", "Square", "Triangle"])
                .value_(oscWave)
                .action_({ |m|
                    oscWave = m.value;
                    Ndef(\source).set(\oscWave, m.value);
                });

            leftCol.decorator.nextLine;
            makeSlider.(leftCol, "frequency (Hz)",
                ControlSpec(20.0, 8000.0, \exp, 0, oscFreq),
                oscFreq,
                { |ez| oscFreq = ez.value; Ndef(\source).set(\oscFreq, ez.value) });

            makeSlider.(leftCol, "vibrato rate (Hz)",
                ControlSpec(0.1, 10.0, \lin, 0, oscVibRate),
                oscVibRate,
                { |ez| oscVibRate = ez.value; Ndef(\source).set(\oscVibRate, ez.value) });

            makeSlider.(leftCol, "vibrato depth (Hz)",
                ControlSpec(0.0, 50.0, \lin, 0, oscVibDepth),
                oscVibDepth,
                { |ez| oscVibDepth = ez.value; Ndef(\source).set(\oscVibDepth, ez.value) });

            // ---- Noise params ----
            leftCol.decorator.nextLine;
            StaticText(leftCol, colWidth@16).string_("  Noise")
                .stringColor_(Color.gray(0.6)).font_(Font.default.copy.italic_(true));

            StaticText(leftCol, 80@26).string_("noise type:")
                .stringColor_(Color.white);
            PopUpMenu(leftCol, 160@26)
                .items_(["White", "Pink", "Brown"])
                .value_(noiseType)
                .action_({ |m|
                    noiseType = m.value;
                    Ndef(\source).set(\noiseType, m.value);
                });

            // ======================================================
            // RIGHT COLUMN: EFFECTS + OUTPUT
            // ======================================================
            sectionLabel.(rightCol, "EFFECTS");

            // ---- Filter ----
            makeBypassButton.(rightCol, "Filter", fxFilterBypass, { |b|
                fxFilterBypass = if(b.value == 0, { 1 }, { 0 });
                Ndef(\fx_filter).set(\bypass, fxFilterBypass);
            });

            StaticText(rightCol, 80@26).string_("type:").stringColor_(Color.white);
            PopUpMenu(rightCol, 160@26)
                .items_(["Lowpass", "Highpass", "Bandpass"])
                .value_(filterType)
                .action_({ |m|
                    filterType = m.value;
                    Ndef(\fx_filter).set(\filterType, m.value);
                });

            rightCol.decorator.nextLine;
            makeSlider.(rightCol, "cutoff (Hz)",
                ControlSpec(20.0, 20000.0, \exp, 0, filterCutoff),
                filterCutoff,
                { |ez| filterCutoff = ez.value; Ndef(\fx_filter).set(\cutoff, ez.value) });

            makeSlider.(rightCol, "resonance (rq)",
                ControlSpec(0.1, 2.0, \lin, 0, filterRq),
                filterRq,
                { |ez| filterRq = ez.value; Ndef(\fx_filter).set(\rq, ez.value) });

            // ---- Chorus ----
            rightCol.decorator.nextLine;
            makeBypassButton.(rightCol, "Chorus", fxChorusBypass, { |b|
                fxChorusBypass = if(b.value == 0, { 1 }, { 0 });
                Ndef(\fx_chorus).set(\bypass, fxChorusBypass);
            });

            rightCol.decorator.nextLine;
            makeSlider.(rightCol, "rate (Hz)",
                ControlSpec(0.1, 5.0, \lin, 0, chorusRate),
                chorusRate,
                { |ez| chorusRate = ez.value; Ndef(\fx_chorus).set(\rate, ez.value) });

            makeSlider.(rightCol, "depth (ms)",
                ControlSpec(0.0, 10.0, \lin, 0, chorusDepth),
                chorusDepth,
                { |ez| chorusDepth = ez.value; Ndef(\fx_chorus).set(\depth, ez.value) });

            makeSlider.(rightCol, "mix",
                ControlSpec(0.0, 1.0, \lin, 0, chorusMix),
                chorusMix,
                { |ez| chorusMix = ez.value; Ndef(\fx_chorus).set(\mix, ez.value) });

            // ---- Phaser ----
            rightCol.decorator.nextLine;
            makeBypassButton.(rightCol, "Phaser", fxPhaserBypass, { |b|
                fxPhaserBypass = if(b.value == 0, { 1 }, { 0 });
                Ndef(\fx_phaser).set(\bypass, fxPhaserBypass);
            });

            rightCol.decorator.nextLine;
            makeSlider.(rightCol, "rate (Hz)",
                ControlSpec(0.1, 5.0, \lin, 0, phaserRate),
                phaserRate,
                { |ez| phaserRate = ez.value; Ndef(\fx_phaser).set(\rate, ez.value) });

            makeSlider.(rightCol, "feedback",
                ControlSpec(0.0, 0.9, \lin, 0, phaserFeedback),
                phaserFeedback,
                { |ez| phaserFeedback = ez.value; Ndef(\fx_phaser).set(\feedback, ez.value) });

            makeSlider.(rightCol, "mix",
                ControlSpec(0.0, 1.0, \lin, 0, phaserMix),
                phaserMix,
                { |ez| phaserMix = ez.value; Ndef(\fx_phaser).set(\mix, ez.value) });

            // ---- Reverb ----
            rightCol.decorator.nextLine;
            makeBypassButton.(rightCol, "Reverb", fxReverbBypass, { |b|
                fxReverbBypass = if(b.value == 0, { 1 }, { 0 });
                Ndef(\fx_reverb).set(\bypass, fxReverbBypass);
            });

            rightCol.decorator.nextLine;
            makeSlider.(rightCol, "decay (s)",
                ControlSpec(0.5, 10.0, \exp, 0, reverbDecay),
                reverbDecay,
                { |ez| reverbDecay = ez.value; Ndef(\fx_reverb).set(\decay, ez.value) });

            makeSlider.(rightCol, "damping",
                ControlSpec(0.0, 1.0, \lin, 0, reverbDamp),
                reverbDamp,
                { |ez| reverbDamp = ez.value; Ndef(\fx_reverb).set(\damp, ez.value) });

            makeSlider.(rightCol, "mix",
                ControlSpec(0.0, 1.0, \lin, 0, reverbMix),
                reverbMix,
                { |ez| reverbMix = ez.value; Ndef(\fx_reverb).set(\mix, ez.value) });

            // ---- Output ----
            rightCol.decorator.nextLine;
            sectionLabel.(rightCol, "OUTPUT");

            makeSlider.(rightCol, "master volume",
                ControlSpec(0.0, 1.0, \lin, 0, masterAmp),
                masterAmp,
                { |ez| masterAmp = ez.value; Ndef(\source).set(\amp, ez.value) });

            rightCol.decorator.nextLine;
            Button(rightCol, 130@28)
                .states_([["Waveform scope", Color.black, Color.gray(0.7)]])
                .action_({ s.scope(numChannels: 2) });

            Button(rightCol, 140@28)
                .states_([["Spectrum scope", Color.black, Color.gray(0.7)]])
                .action_({ FreqScope.new(400, 200, 0, server: s) });

            Button(rightCol, 100@28)
                .states_([["node tree", Color.black, Color.gray(0.7)]])
                .action_({ s.plotTree });

            w.onClose_({
                if(freesoundWin.notNil and: { freesoundWin.isClosed.not }, {
                    freesoundWin.close;
                });
                Ndef(\fx_reverb).clear;
                Ndef(\fx_phaser).clear;
                Ndef(\fx_chorus).clear;
                Ndef(\fx_filter).clear;
                Ndef(\source).clear;
                buf.free;
                "Workbench closed. Ndefs cleared.".postln;
                0.exit;
            });

            w.front;
            "Workbench GUI ready.".postln;
        }.fork(AppClock);

    }).play(AppClock);
});
)
