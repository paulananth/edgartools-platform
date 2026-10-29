# 148: The Name Frequency census is a configured target

Priority: 148. Map: [Rebuild priorities](../map.md). Opened 2026-10-29 07:50 ET, moved out of ticket 135
(operator, 2026-10-29, agreeing to narrow 135 to the population proof).

Type: task. Status: open. Blocked by: none.

## Question

The Name Frequency census (`edgar-warehouse mdm name-census`) is built in Python (`name_frequency.py`,
`name_census.py`; GLEIF's input checked by `gleif_publication.py`) over configured readings. Codex's
`whole-source-census` workstream left open: "Express complete source census construction in bundled Rules,
with immutable source/context receipts and separate worker verification", then replace its consumers and retire
the Python construction. The Company `mastering` target pins the census by its digest. The result was proven
equal to the original sources to EOF on 2026-10-09 (`whole-source-census`, file sha256 recorded there).

## Parts

Claude's (operator, 2026-10-29: "Close out ticket 135 then take 148"; "yes", to taking 148 while ticket 120's
loads run). Built in slices: this PR moves the census's counting into configured reductions; the Bookkeeping
target, its consumers and the Python's retirement follow on their own PRs.

- [x] GoF consult on `name_frequency.py`, `name_census.py` and the combine engine: run late, as the review's GoF axis after slice 1's code (the rule asks for it before code); verdict leave it: `document()` is now a 6-line adapter onto `counted_document()`, one formatter, and the set-based fold retires in a later slice (2026-10-29 18:16 ET)
- [ ] Slice 1, the counting configured: the SEC half read by `census-sec-names.yaml` (each filer's current and
  former name keys beside its CIK) and counted by `census-sec-reduction.yaml` (`held`: each key's CIK count and
  five smallest CIKs; `wanted`: the current-name keys); the GLEIF half counted by
  `rules/sources/gleif/census-name-reduction.yaml` (`max_rows` 4,000,000 for the whole Golden Copy). Python only
  assembles the document (`name_census.counted_document`); the cascade path keeps its own fold
- [x] Slice 1, the SEC half on the whole population equals the recorded census (`cm27-raw/census.json`):
  43,338 filers, 43,245 current-name keys, 0 differing, the population and receipts sha256 equal; 181 s
  (`.scratch/company-mastering/census_sec_half.py`; its output written 2026-10-29 08:04 ET)
- [x] Slice 1 tests: 335 pass over the census, combine, Company preparation, matching and CLI tests, rebased on
  today's `main` (2026-10-29 18:11 ET)
- [ ] Slice 1, the whole census byte-identical to `cm27-raw/census.json` (digest `09c843c9...`), with the GLEIF
  half read from the Golden Copy: about 2½ hours on the machine (operator, 2026-10-29: "Run it this afternoon
  (Recommended)"), after ticket 120's loads and 135's proof. The PR merges only once this is proven: every
  Company bundle binds the census digest
- [x] Slice 1: three-axis review, findings fixed (2026-10-29 18:16 ET). No input on real data gives a different census from main's. Fixed: stale docstrings (`name_frequency.py`, `name_census.py`, `census-sec-reduction.yaml`, `docs/specs/mdm/local-operations.md`); a test holds the four copies of the SEC name-key chain equal (`census-filer.yaml` and `census-sec-names.yaml`, current and former), since a drift changes the census digest; tests through `write_name_frequency` for a crowded name (count 7, the five smallest CIKs and LEIs) and a GLEIF record with no LEI (left out, as main's fold leaves it: run on both, equal; the review expected a refusal from reading the code); the proof script prints counts only. Noted, not changed: the new path refuses where main had no limit, past 65,536 filers (256 readings of 256) or 4,000,000 GLEIF rows (3,021,317 measured); with the cascade on, the Golden Copy is read twice (once by the reduction, once by the fold) until the fold retires
- [ ] Slice 1: PR, CI, merge, after the whole census is proven byte-identical
- [ ] The census as a configured Bookkeeping target (source extract, combine), each step verified by its own
  worker; equal to today's Python census on the whole capture (the 2026-10-09 sha256)
- [ ] Its consumers read the target's output; the Python construction retired, an independent test-only oracle
  kept until the configured one is proven
- [ ] The set-based Python fold retired (`name_census._sec_population`, `fold_reading`, `census`, `document`; `census-raw.yaml`, now read by no code), its tests moved onto the configured path
- [ ] Three-axis review of the whole ticket; PR, CI, merge
- [ ] Learning → skill
