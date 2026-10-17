# A run keeps the mappings it started with

Priority: 103, tier 1. Map: [Rebuild priorities](../map.md).

Type: task (code). Status: in progress. Blocked by: none. From: the source
readiness design (`docs/specs/source-readiness.md`, PR #1036), "Confirmed
synchronization behavior": a consumer run keeps the required versions it
started with, through every batch and on resume; a newer run uses newer ones.

## Question

`execute_manifest` (`edgar_warehouse/mdm/clean/cli.py`) reads each source batch
through `batch_input`, which takes the newest registered mapping
(`current_reading`) for every batch. A mapping registered while a run is part
way through is then read by that run's later batches, and on resume: one run
mixes two readings of the same source. `reading_at` (`store.py`) exists for the
pinned case and has no caller since the GLEIF native reader that used it was
retired (#904). A check at the start of a run cannot fix this, since the
selection happens again per batch.

Fix: the run's frozen scope (`mdm.run.scope`) names the mapping version of
every source its manifest reads, chosen once when the run first starts; every
later call and every resume reads each batch at that pinned version. The
Merge Stage keeps its own checks at commit (the SQL joins
`mdm.dataset_mapping` on each record's mapping version; identity, constraints
and the Bookkeeping lease fence are unchanged).

Out of scope: the other required versions the design names (RDM, matching and
merge policy beyond the manifest's policy digest, Name Frequency, lookup
receipts) and the Change Journal processing identity; each is its own ticket.

## Checklist

- [x] Ticket written; 103 free in every worktree and remote branch; overlap guard clean ("this branch changes no files") (2026-10-17 07:35 ET)
- [x] Pre-code `/gof-refactor-reviewer` consult on `cli.py` and `run.py`: leave the structure. `cli.py` changed 29 times since July, along feature lines rather than one repeated conditional; the change is one parameter and one small function, no pattern (2026-10-17 07:36 ET)
- [x] Failing test first: `tests/integration/test_clean_run_pins_postgres.py` on unchanged code, 2 failed, 1 passed. The resumed run's second batch was stored under mapping 2 with no error; a run naming an unregistered source left a started `mdm.run` row behind. The new-run case passed on both, as it should (2026-10-17 07:38 ET)
- [x] Code: `pinned_mapping_versions` (`cli.py`) picks each manifest source's newest mapping once, before the run starts, across all stages; `RunCoordinator.start` keeps them in the frozen scope as `mapping_versions`; every later call and resume reads each batch through `reading_at` at the pinned version; preview uses an existing run's pins; a scope that pins no reading of a source it reads is refused. `batch_assertions`/`batch_evidence` (no run) still read the newest mapping (2026-10-17 07:39 ET)
- [ ] Tests pass: the new tests and the affected files (named below)
- [ ] Finding recorded: whether a later Bookkeeping run over the same input resumes the old MDM run (effect key)
- [ ] Three-axis review (Standards, Spec, GoF) and fixes
- [ ] PR, CI green; merge only on the operator's word
- [ ] Learning → skill
