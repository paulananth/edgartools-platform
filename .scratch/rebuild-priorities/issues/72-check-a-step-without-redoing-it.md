# Check a step without redoing it

Priority: 72, tier 1, in flight (raised by the operator, 2026-10-13). Map: [Rebuild priorities](../map.md).

Type: grilling. Status: resolved (2026-10-13 ET). Blocked by: none

## Question

Every Bookkeeping step has a check: a separate process, under its own database login, that decides whether the work may be marked done. For three steps the check does the whole work again and compares the outputs:

- `source.read`, which takes the source extract from each file (`edgar_warehouse/workers/source_read.py`, `verify`);
- `source.combine` (`workers/source_combine.py`, `verify`);
- `mdm.prepare` (`workers/mdm_prepare.py`, `verify`).

The other steps' checks read back what was written, without redoing it: `mdm.merge` reads the MDM store, `journal.record` reads the Change Journal, and `mdm.publish` reads the outbox.

What the stopped Company proof of 2026-10-13 measured (process seconds summed over its progress lines; the ratios are what matter):

| Step | Work | Check | Check as % of work |
|---|---|---|---|
| source.read | 2,260 s | 2,529 s | 112% |
| source.combine | 1,387 s | 1,160 s | 84% |
| mdm.prepare | 333 s | 328 s | 99% |
| mdm.merge | 1,062 s | 221 s | 21% (read back) |
| journal.record | 365 s | 200 s | 55% (read back) |

So the checks double the cost of the three largest steps.

**What may a check do instead of redoing the work?**

- **A. Keep it** as it is: every unit is done twice.
- **B. Confirm, don't redo.** The check confirms:
  - the input hashes;
  - the contract digest;
  - the worker's pinned runtime (the engine and code files' hashes) equals the approved one;
  - the output's hash equals its receipt;
  - the output is well formed (it parses, its tables are the declared ones, it stays within bounds).

  It catches: wrong or changed inputs, a different engine or contract, a damaged or cut-off output. It misses: a bug or non-repeatable result inside a pinned engine that writes a wrong but well-formed output, and a worker login misused to write false output.
- **C. B, plus redoing a sample.** The check redoes the work in full for:
  - the first unit of each step in each run;
  - every unit whose runtime or contract digest is new to the store;
  - a random share of the rest (for example 5%).

  A non-repeatable engine shows up within the first run, and a misused worker login is caught with the sample's probability on each unit it writes. The cost is about 5-10% of the work, against 84-112% today.

Recommendation: C. The worker would record its runtime digest beside its output, so the check can compare it.

## Answer

C. Operator, "Confirm, plus a sample (Recommended)" (2026-10-13 20:03 ET).

## Checklist

- [x] The operator's decision: C (2026-10-13 20:03 ET)
- [x] The worker's runtime: no code needed. Each worker already reports its runtime digest with its output, and `bookkeeping.report` pins the first one per run and profile and refuses a changed one ("Pinned worker runtime changed; start a new run", migration 006). GoF consult (2026-10-13 20:17 ET): the choice lives in the shared check loop (`workers/__main__.py`), one `confirm` per step; split combine's input checks from its combining first
- [x] Parse (`source.read`) and combine (`source.combine`) confirm instead of redoing; `mdm.prepare` keeps redoing (its check is about 4% of check time, and its checks and work are one function). `tests/engine/test_check_confirms.py`, 21 pass: confirm passes without running the engine or the combination; it refuses another contract, missing or reordered inputs, an undeclared table, non-row rows, a bad deferred list, another output URI, changed receipts and a changed scope; a wrong value passes confirm and the redo catches it. The input and output hashes stay Bookkeeping's (`input.hash`, `output.receipt`). Affected tests: engine and architecture 449 pass (the 17 failures are the local environment's, the same on main); Bookkeeping Postgres 98 pass, 8 min (2026-10-13 20:17 ET)
- [x] The sample: Bookkeeping now gives each unit its ordinal in the work envelope; a check redoes the step's first unit (ordinal 0) and a draw below 5 of 100 (`secrets.randbelow`, at check time, after the output is written). Each decision (redone, first unit, draw, percent) is written beside the report and named in its proofs, which Bookkeeping verifies (2026-10-13 20:17 ET)
- [x] Review, three axes (2026-10-13 20:23 ET). GoF: leave it. Fixed from Standards and Spec:
  - a streamed source extract was recorded "not redone" though `confirm` redid it: `confirm` now raises `Redo`, and the check loop redoes the unit and records `redone: true` with the reason (a test runs it through the loop);
  - the parse step's confirm compares each input's context and lookup receipts, not only the file (version 2 and 3), and runs the contract's limit checks (shared with the work as `_limits`);
  - combine's confirm refuses an undeclared table, and a reduce output past its row or byte bound;
  - the docs that said the verifier always rebuilds (READING.md, COMBINING.md) now say it confirms, with a sample rebuilt; the Bookkeeping skill describes the rule;
  - "reading" removed from the new text.
  Not taken, with reasons:
  - checking a file's output rows against `max_records`: that limit bounds a file's input records, not the rows it gives, so the check could refuse a valid file;
  - redoing a unit whose contract is new to the store: every step today has one contract per run, so the step's first unit covers a new contract; a step mixing contracts within one run would rely on the 5% draw;
  - generated steps (`ordinal_base` above 0) have no ordinal-0 unit, so they rely on the 5% draw; no step uses generated work today.
  Tests: 25 confirm tests; affected engine tests 190 pass; the guard is clear for READING.md and COMBINING.md, and for `workers/source_*.py`.
- [x] PR, CI green, merge on the operator's word: #958, six checks green, merged as 00e89799 2026-10-13 20:30 ET (operator: "Merge both (Recommended)")
