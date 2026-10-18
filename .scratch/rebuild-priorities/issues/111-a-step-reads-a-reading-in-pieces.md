# A step reads a reading in pieces

Priority: 111, tier 2, the recreation proof (raised by ticket 14's slice 2, 2026-10-18). Map: [Rebuild priorities](../map.md).

Type: task (engine). Status: claimed (Claude, 2026-10-18 ET, branch `claude/t111-read-pieces`). Blocked by: none. Unblocks: 14 (slice 2, OpenFIGI's chain run by `rules test`).

## Why

Bookkeeping freezes every unit of a run before it starts (`bookkeeping/clean/config.py`, `worklist`: "no paths or work are discovered on resume"). OpenFIGI's chain reads its records over each piece of the combine's output (`rules/sources/openfigi/record.yaml`), and how many pieces there are is known only once the combine has run. So that step could not be declared: every Proving Run script built it by hand (`.scratch/onboarding/openfigi/openfigi_run.py`, the record step).

## Design

GoF consult (2026-10-18 18:00 ET), of three options: (a) a worker that emits a sealed expansion, one unit per piece (the engine supports it; no worker emits one); (b) `source.read` takes one input naming a verified reading and reads each of its pieces; (c) fold `record.yaml` into the combine. Recommended (b): every piece already fits one unit (OpenFIGI's run reads them in one read, up to the contract's `max_artifacts`, at most 512); (a) builds fan-out for work that fits one unit; (c) needs a transform language the combine does not have (`combination.rs` joins groups as nested values only).

- **Source input version 4:** `{version: 4, contract, pieces: <a verified reading's receipt>}`. The worker turns it into its own version-1 input: a large reading's (version-2 index) parts are the pieces; a small reading's (version 1) inline rows are each written once beside the step's output, named by their hash (`<output>.pieces/<sha256>.json`), and the verifier reads them back by that hash, so a changed piece fails the check.
- In a target, the step's input is a composed document whose `pieces` slot names the combine's unit: `{compose: {document: {version: 4, contract: ..., pieces: {slot: combined}}, slots: {combined: {step: combine, key: ...}}}}`.
- A reading with more pieces than the contract's `max_artifacts` is refused by the existing artifact-count check: an explicit refusal, never a silent split. Past 512 pieces, option (a) is the next step.

## Checklist

- [x] GoF consult: option (b) (2026-10-18 18:00 ET)
- [x] `source.read` version 4, `edgar_warehouse/workers/source_read.py` `_pieces` (2026-10-18 18:04 ET)
- [ ] ~~Run inside Bookkeeping (the composed `pieces` slot resolved by the engine)~~ deferred to ticket 14 slice 2: proved by reading the code only (`engine.py` `_compose` fills a slot with the unit's `{uri, sha256}`); OpenFIGI's target run by `rules test` is its test
- [x] Three-axis review (2026-10-18 18:08 ET). GoF: reuse the shared index check (`source_readings.index`) instead of a weaker copy (done). Standards and Spec: a reading carrying lookup receipts is refused (its evidence was dropped), each part's entry is checked, inline pieces are written only once the whole input passes its checks, an empty reading's refusal is written down (all done), a combine's own output is tested. `tests/engine/test_read_pieces.py`, 8 passed: a small reading's inline rows, a large reading's parts, a combination, a changed piece failing the verifier, too many pieces, lookup receipts, a malformed index, a refused input writing no piece. Earlier affected-test run: 1,187 passed in 6 min 24 s, over the five-minute limit; named affected files since
- [ ] PR, CI, merge
- [x] Learning → skill: the data-platform skill's READING.md says how a step reads a reading in pieces (version 4)
