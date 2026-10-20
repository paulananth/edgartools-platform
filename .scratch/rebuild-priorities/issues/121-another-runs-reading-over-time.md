# 121: Which runs a reading of another run takes, over time

Priority: 121. Map: [Rebuild priorities](../map.md). Found by ticket 120's
reviews (2026-10-19 18:15 ET).

Type: task. Status: open. Blocked by: none.

## What is open

Ticket 120 lets a step read another source's finished runs
(`{run: {source, target, step}}`, e.g. Securities reading OpenFIGI's
answers). It takes every verified unit of every complete run of that target,
an output two units share listed once. That is right for one capture; over
time:

- **A second capture or a forced rerun:** the same identifier can come back
  in two answers. `figi-pairs.yaml` takes one value per key, so the combine
  refuses ("Group one requires exactly one value per key"). The refusal is
  safe, not silent, but Securities stop.
- **The 256-unit list:** one reading takes at most 256 units. The 2026 Q2
  answers fit only when runs are full 512-file bundles (240 CUSIP, 243 ISIN
  units); smaller bundles or a second capture exceed it, and the manifest is
  refused.
- **Compaction:** Bookkeeping compacts a complete, unpinned run's units after
  30 days. The producing runs' units then disappear; their files are already
  recorded processed, so nothing reruns them, and Securities' manifest finds
  no units.
- **Rechecking cost:** a claim or report of a step that reads another run
  rechecks that run's whole chain: 73 s for \`figi_pairs\` (~480 answer units,
  16 request files each). Securities set a 900 s lease for it; a reading of
  more units needs the recheck bounded (each other-run unit's verification
  kept once, not redone per claim and report).
- **The listing query** filters runs by submission name and target, with no
  index on them (`pipeline_run` is small; recheck at scale).

## Decision needed

Which runs a reading takes (the latest capture's, a capture named by the run,
or the latest unit per identifier), and how a producing run's units are kept
(pinned while read, or a reading's own retained copy).

## Checklist

- [x] Decide the rule (operator, 2026-10-20 08:31 ET): "Latest run, kept while read (Recommended)": a reading takes the newest complete run of the named target only, and that run is not compacted while a reading run names it
- [x] Corrected (2026-10-20 08:32 ET): one capture's answers come in several runs (2026 Q2: 8 per kind), so "latest run" would read an eighth of them; asked again: "All runs of latest capture (Recommended)": every complete run made from the newest capture of the named target, pinned while read (Bookkeeping's compaction already skips a pinned run)
- [x] Implement (2026-10-20 08:53 ET): a manifest names its capture (`target_manifest.py`); the submission keeps it; `verified_units` takes the newest capture's runs; migration 007 keeps a run another live run reads from compaction. Tests: newest capture only, a capture named as text only, kept while read then compacted (`test_configured_bookkeeping_postgres.py`, 65 passed), the manifest's capture (`test_target_manifest.py`, 30 passed), `rules test` end to end (9 passed), the wheel and generated work (7 passed). A forced rerun of the newest capture: same outputs, listed once by sha256 (ticket 120's test)
- [ ] ~~Over 256 units in one capture~~ stays refused with its count ("a reading takes 1..256"); one capture's OpenFIGI answers are 240 and 243 units. Raise only when a capture needs it
- [ ] Existing stores take migration 007 by `bookkeeping migrate` (a function replaced; no table change) before the next Securities run
- [ ] Learning → skill
