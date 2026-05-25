// Global config dictionary
~config = IdentityDictionary.new;

// GSR pairs in canonical order (1-indexed, matching simulator protocol)
// Index 0 = pair (1,2), index 1 = pair (1,3), etc.
~config[\gsrPairs] = [[1,2], [1,3], [1,4], [2,3], [2,4], [3,4]];

// Edge node GSR mapping: for each node (0-indexed), which global GSR pair
// index does each local gsr_mag/gsr_phase index correspond to?
// nil means that local index is unused (node has fewer than 3 GSR pairs).
//
// Derived from TDM schedule:
//   Slot 4: tx=0, rx=1 → pair (0,1) → sim pair (1,2) → global index 0
//   Slot 5: tx=0, rx=2 → pair (0,2) → sim pair (1,3) → global index 1
//   Slot 6: tx=0, rx=3 → pair (0,3) → sim pair (1,4) → global index 2
//   Slot 7: tx=1, rx=2 → pair (1,2) → sim pair (2,3) → global index 3
//   Slot 8: tx=1, rx=3 → pair (1,3) → sim pair (2,4) → global index 4
//   Slot 9: tx=2, rx=3 → pair (2,3) → sim pair (3,4) → global index 5
//
// Per-node RX mapping:
//   Node 0: no RX slots
//   Node 1: slot 4 → local[0] = global 0
//   Node 2: slot 5 → local[0] = global 1; slot 7 → local[1] = global 3
//   Node 3: slot 6 → local[0] = global 2; slot 8 → local[1] = global 4; slot 9 → local[2] = global 5
~config[\nodeGsrMapping] = [
    [nil, nil, nil],  // Node 0: no GSR RX slots
    [0, nil, nil],    // Node 1: local[0] = global pair 0 = (1,2)
    [1, 3, nil],      // Node 2: local[0] = global pair 1 = (1,3), local[1] = global pair 3 = (2,3)
    [2, 4, 5],        // Node 3: local[0] = global pair 2 = (1,4), local[1] = global pair 4 = (2,4), local[2] = global pair 5 = (3,4)
];

"Config loaded.".postln;
