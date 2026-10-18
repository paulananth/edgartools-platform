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
- [x] `source.read` version 4, `edgar_warehouse/workers/source_read.py` `_pieces`; `tests/engine/test_read_pieces.py`, 4 passed. Covers a small reading read from its inline rows, a large one read from its parts with the same rows, a changed inline piece failing the verifier, and more pieces than `max_artifacts` refused. Affected engine and unit tests: 1,187 passed (6 min 24 s locally, over the five-minute limit: a `source.read` change reaches most of the engine suite) (2026-10-18 18:04 ET)
- [ ] Three-axis review, PR, CI, merge
- [ ] Learning → skill: the data-platform skill's READING.md says how a step reads a reading in pieces (version 4)
