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
    ~synths[\collective].set(param, val);
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

// --- Window ---

w = Window("Shrine Controls", Rect(100, 100, 420, 900));
w.view.background = Color.gray(0.15);
w.view.addFlowLayout(8@8, 4@4);

// ============================================================
// PAD VOICES
// ============================================================
sectionLabel.(w.view, "Pad Voices");

EZSlider(w.view, 380@28, "trigRateMin",
    ControlSpec(0.1, 100, \exp, 0, 1),
    { |ez| padSet.(\trigRateMin, ez.value) },
    1, unitWidth: 0, labelWidth: 130
);

EZSlider(w.view, 380@28, "trigRateMax",
    ControlSpec(0.1, 100, \exp, 0, 40),
    { |ez| padSet.(\trigRateMax, ez.value) },
    40, unitWidth: 0, labelWidth: 130
);

EZSlider(w.view, 380@28, "grainDurIdle",
    ControlSpec(0.01, 2.0, \exp, 0, 0.3),
    { |ez| padSet.(\grainDurIdle, ez.value) },
    0.3, unitWidth: 0, labelWidth: 130
);

EZSlider(w.view, 380@28, "grainDurFull",
    ControlSpec(0.01, 2.0, \exp, 0, 0.05),
    { |ez| padSet.(\grainDurFull, ez.value) },
    0.05, unitWidth: 0, labelWidth: 130
);

EZSlider(w.view, 380@28, "filterLo (Hz)",
    ControlSpec(20, 20000, \exp, 0, 300),
    { |ez| padSet.(\filterLo, ez.value) },
    300, unitWidth: 0, labelWidth: 130
);

EZSlider(w.view, 380@28, "filterHi (Hz)",
    ControlSpec(20, 20000, \exp, 0, 8000),
    { |ez| padSet.(\filterHi, ez.value) },
    8000, unitWidth: 0, labelWidth: 130
);

EZSlider(w.view, 380@28, "filterRq",
    ControlSpec(0.01, 2.0, \lin, 0, 0.7),
    { |ez| padSet.(\filterRq, ez.value) },
    0.7, unitWidth: 0, labelWidth: 130
);

EZSlider(w.view, 380@28, "gsrDrift",
    ControlSpec(0.0, 1.0, \lin, 0, 0.1),
    { |ez| padSet.(\gsrDrift, ez.value) },
    0.1, unitWidth: 0, labelWidth: 130
);

EZSlider(w.view, 380@28, "posSpeedMin",
    ControlSpec(0.001, 10, \exp, 0, 0.1),
    { |ez| padSet.(\posSpeedMin, ez.value) },
    0.1, unitWidth: 0, labelWidth: 130
);

EZSlider(w.view, 380@28, "posSpeedMax",
    ControlSpec(0.001, 10, \exp, 0, 2),
    { |ez| padSet.(\posSpeedMax, ez.value) },
    2, unitWidth: 0, labelWidth: 130
);

// ============================================================
// COLLECTIVE VOICE
// ============================================================
w.view.decorator.nextLine;
sectionLabel.(w.view, "Collective Voice");

EZSlider(w.view, 380@28, "baseFreqMin (Hz)",
    ControlSpec(10, 500, \exp, 0, 40),
    { |ez| collSet.(\baseFreqMin, ez.value) },
    40, unitWidth: 0, labelWidth: 130
);

EZSlider(w.view, 380@28, "baseFreqMax (Hz)",
    ControlSpec(10, 500, \exp, 0, 120),
    { |ez| collSet.(\baseFreqMax, ez.value) },
    120, unitWidth: 0, labelWidth: 130
);

EZSlider(w.view, 380@28, "collFilterLo (Hz)",
    ControlSpec(20, 20000, \exp, 0, 200),
    { |ez| collSet.(\collFilterLo, ez.value) },
    200, unitWidth: 0, labelWidth: 130
);

EZSlider(w.view, 380@28, "collFilterHi (Hz)",
    ControlSpec(20, 20000, \exp, 0, 4000),
    { |ez| collSet.(\collFilterHi, ez.value) },
    4000, unitWidth: 0, labelWidth: 130
);

EZSlider(w.view, 380@28, "gsrActiveThreshold",
    ControlSpec(0.0, 1.0, \lin, 0, 0.1),
    { |ez| collSet.(\gsrActiveThreshold, ez.value) },
    0.1, unitWidth: 0, labelWidth: 130
);

// ============================================================
// OUTPUT MIXER
// ============================================================
w.view.decorator.nextLine;
sectionLabel.(w.view, "Output Mixer");

EZSlider(w.view, 380@28, "collMixMin",
    ControlSpec(0.0, 1.0, \lin, 0, 0.1),
    { |ez| mixSet.(\collMixMin, ez.value) },
    0.1, unitWidth: 0, labelWidth: 130
);

EZSlider(w.view, 380@28, "collMixMax",
    ControlSpec(0.0, 1.0, \lin, 0, 0.6),
    { |ez| mixSet.(\collMixMax, ez.value) },
    0.6, unitWidth: 0, labelWidth: 130
);

EZSlider(w.view, 380@28, "revMixMin",
    ControlSpec(0.0, 1.0, \lin, 0, 0.05),
    { |ez| mixSet.(\revMixMin, ez.value) },
    0.05, unitWidth: 0, labelWidth: 130
);

EZSlider(w.view, 380@28, "revMixMax",
    ControlSpec(0.0, 1.0, \lin, 0, 0.4),
    { |ez| mixSet.(\revMixMax, ez.value) },
    0.4, unitWidth: 0, labelWidth: 130
);

EZSlider(w.view, 380@28, "reverbDamp",
    ControlSpec(0.0, 1.0, \lin, 0, 0.5),
    { |ez| mixSet.(\reverbDamp, ez.value) },
    0.5, unitWidth: 0, labelWidth: 130
);

EZSlider(w.view, 380@28, "reverbRoom",
    ControlSpec(0.0, 1.0, \lin, 0, 0.7),
    { |ez| mixSet.(\reverbRoom, ez.value) },
    0.7, unitWidth: 0, labelWidth: 130
);

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
