# Rank several sources

Part of the `data-profiling` skill: [SKILL.md](SKILL.md) says when to read this.

## Rank several sources: which one a field trusts first

A master field takes its value from the first source in its priority list
that supplies it (the kind's `defaults.sources`, or a field's own `sources`).
Set that order from the data, not by hand: measure every source of the kind
together.

```
uv run --with duckdb --with pyyaml python rank_sources.py \
  --source <name>=<records file>:<key> [--source ...] \
  --field <field>=<source>:<column or dotted path>[,<source>:<column>...] [--field ...] \
  --out <folder>
```

- **Inputs:** each source's records after its source extract (JSON Lines,
  JSON, CSV or Parquet), keyed by the identifier the sources share. A raw
  response that does not carry that identifier cannot be joined: use the
  extracted records. Pass rows before any reduction to one value (one row per
  delivery or per filer, the key repeated), so a source's disagreement with
  itself is measured; a reduced record hides it.
- **A field** names, per source, a column or a dotted path into nested
  records; a list on the way is walked. Values are compared normalised (upper
  case, punctuation and spaces folded).
- **What it measures, per field and source:** coverage (the keys it fills, of
  all keys any source fills), one value (of its keys, those with exactly one
  value), and agreement pair by pair (of the keys two sources both fill, those
  where they share a value). Never agreement with a majority: two sources
  repeating one origin's words agree and can both be wrong.
- **The order it recommends:** by one value, then coverage. The first source
  wins wherever it fills the field, so it should state one value; each next
  source fills the gaps of those before it. One order per field (a field's
  `sources`) and one for the kind (`defaults.sources`). Sources equal on both
  measures are listed as tied: the operator decides between them.
- **Name each source by its source code**, so `merge_rules` in the output
  (also at the end of `RANKING.md`) pastes into the kind file as it is:
  `defaults.sources`, and `fields.<field>.sources` for each field whose order
  differs.
- **Advice only.** Bring the operator the numbers and the order, one
  question; the operator's ruling stands even where the numbers argue
  otherwise (then show them). refining-rules applies the order, a source's
  Dataset Contract must map the field for its rank to matter, and the change
  is counted against the master records before and after.
- It writes names and counts only, so the files may go in the repository.
