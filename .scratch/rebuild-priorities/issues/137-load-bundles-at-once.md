# 137: Load the bundles of one target at once

Priority: 137. Map: [Rebuild priorities](../map.md). Opened 2026-10-25 13:39 ET.

Type: task. Status: in progress (Claude, branch `claude/t137-bundles-at-once`).
Blocked by: none. Follows [136](136-one-command-loads-a-capture.md).

## Found (2026-10-25 13:38 ET)

The first bundle of `edgar-warehouse load` (OpenFIGI `mastering_cusip`, 512
documents, 6 workers) took 34.6 minutes:

- prepare and submit: about 5 min
- 512 request units: 14 min (13:04–13:18 ET). The workers claimed all of
  them at once; the one verifier checked them one at a time, about 1.6 s each
- 32 answer units: 1.5 min
- the one-unit steps: 10 min (merge 5.7 min)
- finalize: 4 min

8 CUSIP and 8 ISIN bundles one after another is about 9 hours before
Securities. The operator's window is 1–2 hours (operator, 2026-10-24: "10
hours will never fly must be within 1-2 hours").

## Design

`load --bundles N` loads N bundles at once. Each is its own run with its own
verifier. The old skill already said "bundles of one target that do not read
each other are one wave, not a queue", and the MDM spec already settles
concurrent merges (`docs/specs/mdm/recovery.md`: two workers merging
overlapping subjects serialize and revalidate the closure, and deadlocks get
bounded retries). So this follows rulings already given; it is not a new
kind of decision. A bundle that stops does not stop the others, and every
stop is named at the end. Open runs are finished the same way, N at a time.

## Checklist

- [x] `--bundles N`: bundles and open runs N at once, results in bundle order, each stop named at the end (2026-10-25 13:39 ET)
- [x] Tests (2026-10-25 13:39 ET): `test_rules_loading.py` 11 passed; a pool of one fails the at-once test; skill and driver tests 53 passed
- [x] data-operations "Fit the load into the window": a run's verifier is the bound; spread over runs with `--bundles`; measure one bundle first (2026-10-25 13:39 ET)
- [x] GoF consult (2026-10-25 13:39 ET, made after the code, against the hard rule's order): leave it. A thread pool is the language's own facility, and one `at_once` helper serves both open runs and bundles
- [x] Three-axis review (2026-10-25 13:43 ET). GoF: leave it. Standards and Spec: no shared-state race; fixed and tested:
  - [x] After the deadline no queued bundle starts; they are named once (`test_after_the_deadline_no_bundle_starts...`)
  - [x] Any failure, not only a stop, is named with its bundle and the others go on (`test_any_failure_is_named_with_its_bundle`)
  - [x] The at-once test waits on a barrier, not on timing; a stop with bundles still queued is tested (`--bundles 1`)
  - [x] The skill names `--bundles` and the number of bundles apart
  - Tests: `test_rules_loading.py` 13 passed
- [ ] PR, CI green, merge
- [ ] 120's load restarted with `--bundles`, the total stated before it starts
- [ ] Learning → skill
