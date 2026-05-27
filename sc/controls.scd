// Shrine Controls — live parameter panel
// Load manually:
//   thisProcess.interpreter.executeFile("/path/to/shrine/sc/controls.scd");
//
// Requires: startup.scd must have been run so ~synths is populated.
(
var w;

// --- Helpers ---

var padSet = { |param, val|
    ~synths[\padVoices].do { |s| s.set(param, val) };
};

var collSet = { |param, val|
    ~synths[\pairVoices].do { |s| s.set(param, val) };
    ~synths[\triadVoices].do { |s| s.set(param, val) };
};

var mixSet = { |param, val|
    ~synths[\outputMixers].do { |s| s.set(param, val) };
};

var sectionLabel = { |parent, text|
    var label = StaticText(parent, Rect(0, 0, 380, 24));
    label.string = text;
    label.font = Font.default.copy.bold_(true).size_(13);
    label.stringColor = Color.white;
    label;
};

var makeSlider = { |parent, label, spec, action, initVal|
    var ez = EZSlider(parent, 380@28, label, spec, action, initVal,
        unitWidth: 0, labelWidth: 130);
    ez.labelView.stringColor = Color.white;
    ez.numberView.stringColor = Color.white;
    ez.numberView.normalColor = Color.white;
    ez.numberView.typingColor = Color.cyan;
    ez.numberView.background = Color.gray(0.25);
    ez;
};

// --- Window ---

w = Window("Shrine Controls", Rect(100, 100, 420, 900));
w.view.background = Color.gray(0.15);
w.view.addFlowLayout(8@8, 4@4);

// ============================================================
// PAD VOICES
// ============================================================
sectionLabel.(w.view, "Pad Voices");

makeSlider.(w.view,"trigRateMin",
    ControlSpec(0.1, 100, \exp, 0, 1),
    { |ez| padSet.(\trigRateMin, ez.value) },
    1);

makeSlider.(w.view,"trigRateMax",
    ControlSpec(0.1, 100, \exp, 0, 40),
    { |ez| padSet.(\trigRateMax, ez.value) },
    40);

makeSlider.(w.view,"grainDurIdle",
    ControlSpec(0.01, 2.0, \exp, 0, 0.3),
    { |ez| padSet.(\grainDurIdle, ez.value) },
    0.3);

makeSlider.(w.view,"grainDurFull",
    ControlSpec(0.01, 2.0, \exp, 0, 0.05),
    { |ez| padSet.(\grainDurFull, ez.value) },
    0.05);

makeSlider.(w.view,"filterLo (Hz)",
    ControlSpec(20, 20000, \exp, 0, 300),
    { |ez| padSet.(\filterLo, ez.value) },
    300);

makeSlider.(w.view,"filterHi (Hz)",
    ControlSpec(20, 20000, \exp, 0, 8000),
    { |ez| padSet.(\filterHi, ez.value) },
    8000);

makeSlider.(w.view,"filterRq",
    ControlSpec(0.01, 2.0, \lin, 0, 0.7),
    { |ez| padSet.(\filterRq, ez.value) },
    0.7);

makeSlider.(w.view,"gsrDrift",
    ControlSpec(0.0, 1.0, \lin, 0, 0.1),
    { |ez| padSet.(\gsrDrift, ez.value) },
    0.1);

makeSlider.(w.view,"posSpeedMin",
    ControlSpec(0.001, 10, \exp, 0, 0.1),
    { |ez| padSet.(\posSpeedMin, ez.value) },
    0.1);

makeSlider.(w.view,"posSpeedMax",
    ControlSpec(0.001, 10, \exp, 0, 2),
    { |ez| padSet.(\posSpeedMax, ez.value) },
    2);

// ============================================================
// COLLECTIVE VOICE
// ============================================================
w.view.decorator.nextLine;
sectionLabel.(w.view, "Collective Voice");

makeSlider.(w.view,"baseFreqMin (Hz)",
    ControlSpec(10, 500, \exp, 0, 40),
    { |ez| collSet.(\baseFreqMin, ez.value) },
    40);

makeSlider.(w.view,"baseFreqMax (Hz)",
    ControlSpec(10, 500, \exp, 0, 120),
    { |ez| collSet.(\baseFreqMax, ez.value) },
    120);

makeSlider.(w.view,"collFilterLo (Hz)",
    ControlSpec(20, 20000, \exp, 0, 200),
    { |ez| collSet.(\collFilterLo, ez.value) },
    200);

makeSlider.(w.view,"collFilterHi (Hz)",
    ControlSpec(20, 20000, \exp, 0, 4000),
    { |ez| collSet.(\collFilterHi, ez.value) },
    4000);

makeSlider.(w.view,"gsrActiveThreshold",
    ControlSpec(0.0, 1.0, \lin, 0, 0.1),
    { |ez| collSet.(\gsrActiveThreshold, ez.value) },
    0.1);

// ============================================================
// OUTPUT MIXER
// ============================================================
w.view.decorator.nextLine;
sectionLabel.(w.view, "Output Mixer");

makeSlider.(w.view,"collMixMin",
    ControlSpec(0.0, 1.0, \lin, 0, 0.1),
    { |ez| mixSet.(\collMixMin, ez.value) },
    0.1);

makeSlider.(w.view,"collMixMax",
    ControlSpec(0.0, 1.0, \lin, 0, 0.6),
    { |ez| mixSet.(\collMixMax, ez.value) },
    0.6);

makeSlider.(w.view,"revMixMin",
    ControlSpec(0.0, 1.0, \lin, 0, 0.05),
    { |ez| mixSet.(\revMixMin, ez.value) },
    0.05);

makeSlider.(w.view,"revMixMax",
    ControlSpec(0.0, 1.0, \lin, 0, 0.4),
    { |ez| mixSet.(\revMixMax, ez.value) },
    0.4);

makeSlider.(w.view,"reverbDamp",
    ControlSpec(0.0, 1.0, \lin, 0, 0.5),
    { |ez| mixSet.(\reverbDamp, ez.value) },
    0.5);

makeSlider.(w.view,"reverbRoom",
    ControlSpec(0.0, 1.0, \lin, 0, 0.7),
    { |ez| mixSet.(\reverbRoom, ez.value) },
    0.7);

// ============================================================
// DEBUG BUTTONS
// ============================================================
w.view.decorator.nextLine;

Button(w.view, 115@28)
    .states_([["scope", Color.black, Color.gray(0.75)]])
    .action_({ s.scope });

Button(w.view, 115@28)
    .states_([["meter", Color.black, Color.gray(0.75)]])
    .action_({ s.meter });

Button(w.view, 115@28)
    .states_([["plotTree", Color.black, Color.gray(0.75)]])
    .action_({ s.plotTree });

// No closeAction — window close does not affect synths.

w.front;
)
