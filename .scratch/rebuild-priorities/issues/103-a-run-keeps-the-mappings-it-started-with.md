# A run keeps the mappings it started with

Priority: 103, tier 1. Map: [Rebuild priorities](../map.md).

Type: task (code). Status: in review (draft PR). Blocked by: none. From: the source
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

- [x] Ticket written; 103 free in every worktree and remote branch; overlap guard clean ("this branch changes no files"); every other `claude/*` branch and worktree checked for the changed paths: only `claude/identifier-index-pending` touches them, already merged as #1007 (2026-10-17 07:35 ET; Claude branches checked 07:55 ET)
- [x] Pre-code `/gof-refactor-reviewer` consult on `cli.py` and `run.py`: leave the structure. `cli.py` changed 29 times since July, along feature lines rather than one repeated conditional; the change is one parameter and one small function, no pattern (2026-10-17 07:36 ET)
- [x] Failing test first: `tests/integration/test_clean_run_pins_postgres.py` on unchanged code, 2 failed, 1 passed. The resumed run's second batch was stored under mapping 2 with no error; a run naming an unregistered source left a started `mdm.run` row behind. The new-run case passed on both, as it should (2026-10-17 07:38 ET)
- [x] Code: `pinned_mapping_versions` (`cli.py`) picks each manifest source's newest mapping once, before the run starts, across all stages; `RunCoordinator.start` keeps them in the frozen scope as `mapping_versions`; every later call and resume reads each batch through `reading_at` at the pinned version; preview uses an existing run's pins; a scope that pins no reading of a source it reads is refused. `batch_assertions`/`batch_evidence` (no run) still read the newest mapping. Verified by the same three tests, now 3 passed (2026-10-17 07:39 ET)
- [x] Tests pass: `test_clean_run_pins_postgres.py` 3, `test_clean_run_postgres.py` and `test_mdm_merge_worker_postgres.py` 11, `test_clean_quality.py` and `test_clean_gleif_publication.py` 103, the reading tests of `test_clean_mdm_postgres.py` 5; all passed, each under 30 s (2026-10-17 07:44 ET)
- [x] Wider affected run: `pytest --testmon` over `tests/mdm`, `tests/unit`, `tests/architecture`, `tests/integration`: 2145 passed, 1 expected failure. It took 9 min 25 s, over the five-minute local limit: testmon had no record for most of these tests and ran them all. Narrow it to named files next time (2026-10-17 07:49 ET)
- [x] Finding: which run a later Bookkeeping run resumes. The worker's MDM run id is `uuid5(effect_key)`, and the effect key hashes the submitted Rules export, step, key and unit (`bookkeeping/clean/engine.py:329`). A mapping is registered only by activating a source Rules version (`rules/db.py:210`). A run submitted from that source version therefore gets a new effect key and a new MDM run, which pins the new mapping. A run submitted from a pipeline Rules version does not change when a source mapping changes, so the same unit resumes the old MDM run. That was already so before this ticket (its committed batches were skipped); it is the design's Change Journal processing-identity requirement, a follow-up (below), not this slice (2026-10-17 07:43 ET)
- [x] Three-axis review. GoF: leave it. Standards: the code part's verification was not named (fixed above); the unregistered-source check is now only on the unpinned path, where it can fire; the long call reformatted. Spec: the old-scope case and the all-stages refusal, both kept and recorded below; the worker (`mdm_merge.execute`) resumes by calling `execute_manifest` again with the same run id, so the resume test covers its path; no separate worker test. The race of two first starts fails closed in `mdm.start_run` ("Root run scope changed"), untested here (2026-10-17 07:44 ET)
- [ ] PR #1037 (draft), CI green; merge only on the operator's word
- [ ] Map entry under "Decisions so far" once merged, as the map records merged tickets
- [x] Learning → skill (added after the three-axis review; skill tests 72 passed): `skills/mdm-engineering/SKILL.md`, Writes and transactions, gains "A run reads what it started with": pin a dependency registered anew mid-run in the run's frozen scope at first start; never resolve it again per batch (2026-10-17 07:50 ET)

## Decisions that follow from the design

- A run scope written before this ticket names no mapping versions; resuming such a run that reads a source is refused ("Run scope pins no reading of ..."). The shared local MDM held 0 runs, 0 entities and 0 registered mappings when read on 2026-10-17 07:40 ET, and the rebuild keeps no old behaviour, so nothing is stranded.
- Pins cover every source the manifest reads, in every stage, and a source that is not registered refuses the run before it starts: the design's "block required inputs" for the whole run, rather than failing part way.

## Follow-ups (not this ticket)

- Change Journal processing identity: a file must be reconsidered when a dependency it was processed under changes (a source mapping, RDM, matching and merge policy, Name Frequency, lookup receipts), and a pipeline-submitted MDM run must not resume across such a change. New ticket, after this one merges.
- The other required versions (RDM, Name Frequency, lookup receipts) pinned for a whole run the same way. New ticket.

## Source readiness gaps, mapped to existing tickets

From the nine-source audit in `docs/specs/source-readiness.md` (PR #1036). None of the nine meets the common-command target; this list only says where each gap is already tracked.

| Gap | Sources | Tracked by |
| --- | --- | --- |
| Approved acquisition authority, so normal activation registers the source's mappings | 8 of 9 (all but `sec.submissions.company`) | 71 (Company, GLEIF, Person activation parts); the others: none yet |
| `rules run --target mdm` end to end | all | 71 (part from ticket 02) and 13 (run a source into MDM) |
| N-PORT run construction: quarter `period`, publication key and revision, lookup producers | `sec.nport.registrant`, `sec.nport.fund`, `sec.nport.security` | 79 (claimed, `claude/nport-onboarding`) |
| Security cross-references from OpenFIGI | `sec.nport.security` (consumer) | 80 |
| GLEIF Level 1's `nport_issuer` record extras | `gleif` | 71 (part from tickets 22 and 97) |
| A source-specific preparation command replaced by the common path | `sec.submissions.company` (`prepare-clean-company`), `sec.submissions.person` (`prepare-capture`) | none yet |
| Read, combine, prepare and processed path | `iapd.adv`, `sec.ownership`, `sec.thirteenf.information_table`, `gleif` members | none yet (ADV matching rules are 76) |

No source was activated, no shared store was written and no provider was asked anything for this map.
