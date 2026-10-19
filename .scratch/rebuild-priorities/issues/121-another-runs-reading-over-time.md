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
- **The listing query** filters runs by submission name and target, with no
  index on them (`pipeline_run` is small; recheck at scale).

## Decision needed

Which runs a reading takes (the latest capture's, a capture named by the run,
or the latest unit per identifier), and how a producing run's units are kept
(pinned while read, or a reading's own retained copy).

## Checklist

- [ ] Decide the rule (operator)
- [ ] Implement, with a test per case (second capture, forced rerun, compaction, over 256)
- [ ] Learning → skill
