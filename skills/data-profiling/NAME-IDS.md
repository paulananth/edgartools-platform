# An id from a name

Part of the `data-profiling` skill: [SKILL.md](SKILL.md) says when to read this.

## An id from a name: only when no id exists

Ids and cross-reference ids always come first. Only for records that carry
none, in either source, is an id made from the name. A fixed precision bar
does not make a name safe: names one token apart are often different entities
(a share class, a series number, a legal form). So learn from the data first:

```
uv run --with duckdb --with pyyaml python match_names.py \
  --left <file> --left-key <col> --left-name <col> [--left-variants <col>] \
  --right <file> --right-key <col> --right-name <col> [--right-variants <col>] \
  [--same <left col>=<right col>] [--attribute <left col>=<right col> ...] [--personal] --out <folder>
```

- **Compare exactly:** token pairs that tell records with different keys apart.
  The id keeps them.
- **May fold:** variants seen on one entity (its other names, or a pair a
  shared id proves) and never apart. `name_id@1` does not fold them; the
  report counts how many records would pair one to one with them folded, as
  evidence for a later format version. A rename is not a variant: check the
  examples before proposing a fold.
- **Name alone cannot decide:** pairs seen both ways. A supporting attribute
  (one that agrees on proved pairs and separates near-homonyms) must decide;
  without one the records stay apart.
- **The id** (`name_id@1`): the name's tokens, every one kept, hashed. It is
  the engine's cross-reference format of the same name, so it goes into the
  MDM cross-reference table through the contract, with no code:
  `cross_references: {name_id: <name path>}` and
  `cross_reference_formats: {name_id: name_id@1}`. Like every cross-reference
  it is lookup only: `mdm.cross_reference_lookup('name_id', <id>)` finds the
  records of any source with that name; it never joins records.
- The report shows how many records it would pair one to one across the two
  sources, how many names are held twice (those pair nothing), and, on pairs a
  shared id proves, where the name id agrees and where it contradicts.
- Pass `--personal` when the names are people's, so examples keep their shape
  only.

Propose `name_id` only for a source whose records carry no id the other
sources share. Bring the operator the pairings and contradictions; never
present a name pairing where an id exists.
