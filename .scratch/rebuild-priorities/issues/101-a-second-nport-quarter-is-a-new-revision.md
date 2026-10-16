# A second N-PORT quarter is a new revision of its records

Priority: 101, tier 2. Map: [Rebuild priorities](../map.md).

Type: task (configuration first). Status: open, not started. Blocked by: none. Found by: 100 (An N-PORT link starts at its quarter's data set).

## Question

Each quarter's N-PORT records come out of `mdm.prepare` as revision 1 of the same subjects (one per CUSIP), so the Merge Stage refuses a second quarter ("Source native revision has contradictory publications"; ticket 100's check, 2026-10-16). How does a later quarter become a later revision of the same records, by configuration, so a Security's filed words and its links carry forward and a link keeps its first observed start?

## Checklist

- [ ] Find how other per-period feeds number revisions (13F, ADV) and whether `mdm.prepare` or the contract can take the quarter as the revision
- [ ] Configuration, and a two-quarter check: the second quarter applies, the link keeps its first start
- [ ] If configuration cannot, write the code ticket and ask before coding
- [ ] PR, CI green, merge on the operator's word
- [ ] Learning → skill
