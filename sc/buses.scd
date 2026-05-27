~buses = IdentityDictionary.new;

// 4 consecutive capacitive touch buses (one per pad), 0-indexed.
// Consecutive allocation is REQUIRED for \c_setn in the flush timer.
// Individual pad: ~buses[\cap].index + padIndex
~buses[\cap] = Bus.control(s, 4);

// 6 consecutive GSR magnitude buses (one multichannel allocation).
// Individual pair: ~buses[\gsrMag].index + pairIndex
// Consecutive allocation is REQUIRED for In.kr(gsrMagBuses, 6) in output_mixer.
~buses[\gsrMag] = Bus.control(s, 6);

// 6 consecutive GSR phase buses
~buses[\gsrPhase] = Bus.control(s, 6);

// Audio buses for internal routing (between voice synths and effects)
// 4 mono audio buses, one per pad voice → its output channel
~buses[\padAudio] = 4.collect({ Bus.audio(s, 1) });

// 4 mono audio buses for per-pad collective voice summing.
// Each pad's output mixer reads its own collective bus.
// Pair and triad voices write (sum) into the relevant pads' buses.
~buses[\collectiveAudio] = 4.collect({ Bus.audio(s, 1) });

"Buses allocated.".postln;
4.do({ |i| ("  cap[" ++ i ++ "] = bus " ++ (~buses[\cap].index + i)).postln });
("  gsrMag base = bus " ++ ~buses[\gsrMag].index ++ " (6 consecutive)").postln;
("  gsrPhase base = bus " ++ ~buses[\gsrPhase].index ++ " (6 consecutive)").postln;
