~buses = IdentityDictionary.new;

// 4 capacitive touch buses (one per pad), 0-indexed
~buses[\cap] = 4.collect({ Bus.control(s, 1) });

// 6 consecutive GSR magnitude buses (one multichannel allocation).
// Individual pair: ~buses[\gsrMag].index + pairIndex
// Consecutive allocation is REQUIRED for In.kr(gsrMagBuses, 6) in collective_voice.
~buses[\gsrMag] = Bus.control(s, 6);

// 6 consecutive GSR phase buses
~buses[\gsrPhase] = Bus.control(s, 6);

// Audio buses for internal routing (between voice synths and effects)
// 4 mono audio buses, one per pad voice → its output channel
~buses[\padAudio] = 4.collect({ Bus.audio(s, 1) });

// 1 mono audio bus for the collective voice
~buses[\collectiveAudio] = Bus.audio(s, 1);

"Buses allocated.".postln;
~buses[\cap].do({ |b, i| ("  cap[" ++ i ++ "] = bus " ++ b.index).postln });
("  gsrMag base = bus " ++ ~buses[\gsrMag].index ++ " (6 consecutive)").postln;
("  gsrPhase base = bus " ++ ~buses[\gsrPhase].index ++ " (6 consecutive)").postln;
