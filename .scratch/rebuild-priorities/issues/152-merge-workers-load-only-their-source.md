# 152: Merge workers load only the rules their source needs

Priority: 152. Map: [Rebuild priorities](../map.md). Opened 2026-11-01 11:03 ET, from [ticket 32](32-profiling-08-recreation-proof.md).

Type: task. Status: open. Blocked by: none.

## Question

The `mdm.merge` and `mdm.publish` workers read `rules/sources/<SEC Company>/census-filer.yaml` when `name_census.py` is
imported, for every source. A rules folder without that file cannot merge anything, a GLEIF or Person batch included;
the recreation proof's second agent hit this. Should the file load only when the Name Census is used?

## Parts

- [ ] A test merges a source from a rules folder without the file
- [ ] The file loads when the Name Census is used, not at import
- [ ] PR, CI green, merged
- [ ] `Learning → skill`
