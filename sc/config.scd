// Global config dictionary
~config = IdentityDictionary.new;

// GSR pairs in canonical order (1-indexed, matching simulator protocol)
// Index 0 = pair (1,2), index 1 = pair (1,3), etc.
~config[\gsrPairs] = [[1,2], [1,3], [1,4], [2,3], [2,4], [3,4]];

// Edge node GSR mapping: for each node (0-indexed), which global GSR pair
// index does each local gsr_mag index correspond to?
//
// FDM symmetric mapping: each node measures GSR magnitude toward 3 other
// nodes as (id+1)%4, (id+2)%4, (id+3)%4. Every pair is measured from
// both ends (last-write-wins).
//
//   Node 0: gsr_mag[0]→(0,1)=idx 0, gsr_mag[1]→(0,2)=idx 1, gsr_mag[2]→(0,3)=idx 2
//   Node 1: gsr_mag[0]→(1,2)=idx 3, gsr_mag[1]→(1,3)=idx 4, gsr_mag[2]→(0,1)=idx 0
//   Node 2: gsr_mag[0]→(2,3)=idx 5, gsr_mag[1]→(0,2)=idx 1, gsr_mag[2]→(1,2)=idx 3
//   Node 3: gsr_mag[0]→(0,3)=idx 2, gsr_mag[1]→(1,3)=idx 4, gsr_mag[2]→(2,3)=idx 5
~config[\nodeGsrMapping] = [
    [0, 1, 2],   // Node 0
    [3, 4, 0],   // Node 1
    [5, 1, 3],   // Node 2
    [2, 4, 5],   // Node 3
];

"Config loaded.".postln;
