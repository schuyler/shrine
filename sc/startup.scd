// Shrine / MiniCAT — SuperCollider sound engine
// Entry point: sclang runs this file via systemd or manually.
(
s = Server.default;
s.options.numOutputBusChannels = 4;
s.options.numInputBusChannels  = 0;

// Ensure sclang is listening on the OSC port even on platforms that don't
// open it by default.
thisProcess.openUDPPort(57120);

s.waitForBoot({
    Routine({
        var base = PathName(thisProcess.nowExecutingPath).pathOnly;

        // Phase 1: Load config into global dictionary
        thisProcess.interpreter.executeFile(base +/+ "config.scd");
        "Phase 1: config loaded.".postln;

        // Phase 2: Allocate control and audio buses
        thisProcess.interpreter.executeFile(base +/+ "buses.scd");
        "Phase 2: buses allocated.".postln;

        // Phase 3: Register OSC handlers (writes to control buses)
        thisProcess.interpreter.executeFile(base +/+ "osc-input.scd");
        "Phase 3: OSC handlers registered.".postln;

        // Phase 4: Load palette SynthDefs
        // .add is asynchronous — s.sync waits for all pending defs to reach scsynth.
        // s.sync MUST be called inside a Routine — it silently does nothing outside one.
        thisProcess.interpreter.executeFile(base +/+ "palettes/granular.scd");
        s.sync;
        "Phase 4: palette SynthDefs loaded.".postln;

        // Phase 5: Create groups, instantiate synths, wire buses
        thisProcess.interpreter.executeFile(base +/+ "routing.scd");
        "Phase 5: routing complete.".postln;

        "".postln;
        "Shrine startup complete.".postln;
    }).play(AppClock);
});
)
