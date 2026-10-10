# Bookkeeping without legacy or custom code for Company and Person

Type: task (code), several PRs
Status: in progress (Claude, branch `claude/bookkeeping-independent`)
Blocked by: none for 20a and 20b; 20c needs 15 (done); 20d needs 20c
Blocks: 04 (the end-to-end `rules run` proof), 06 (the source switch-ons), 12, 17 (absorbed into 20c)

## Request

Operator, 2026-10-02 17:51 ET: "fix bookkeeping no legacy or custom code for company and person".

This is the explicit instruction that Codex's design ticket (`.planning/workstreams/bookkeeping-loader-independent-design/TICKET.md`) waits for before Claude implements. The design is `skills/bookkeeping/DESIGN.md`, and the acceptance gates are in `skills/bookkeeping/INDEPENDENCE.md`.

## What the words decide

- **No legacy:** Company and Person workers do not wrap `bookkeeping/clean/company.py`, `stage_company_loader`, `company_source.py` or the Person fixture conversion. The design allowed today's loaders inside external workers; the operator's words rule that out for Company and Person.
- **No custom code:** Company and Person are read by the configured engine (ticket 15) from their rules files. Where the engine can't state something (individual-filer classification, address conversion, filing-array expansion, Company grouping), the engine gets a generic primitive, tested on its own. A Company- or Person-named Python step is not the fallback. This narrows ticket 08's "a custom step as the last resort" for these two kinds.
- **Bookkeeping is control only:** no domain imports, no callback registry, no branches on operation names (GoF consult, 2026-10-02 17:57 ET: remove the `Registry`/`Capability` layer and the Journal operation branches; keep the SQL lifecycle and migrations).

## Not changed by this ticket

- Zero SEC requests still holds. Removing the coupled path lifts the #785 blocker on ticket 06, but the SEC Company acquisition proof still needs a real fetch, on the operator's permission.
- No "independent" claim until gates 1–4 of `INDEPENDENCE.md` have run.

## The protocol (20a), pull not push

Workers pull work through `edgar-warehouse bookkeeping …` commands that print JSON; Bookkeeping spawns nothing and names no worker module. (Built under these names; Codex's design calls them `submit`, `verify_claim` and `verify_report`.)

- Submission is `rules run` (Bookkeeping's `start`): it freezes the approved Rules export and the input manifest, and does no work.
- `claim <run> --profile P --limit N`: task envelopes (run, step, key, attempt, lease proof, deadline, the resolved input, the frozen Rules reference, the intended output, the effect key, the step's domain checks). The step's `operation` names the worker profile. A reported unit is never handed to a worker.
- `renew --envelope -`: renew the lease while the worker runs.
- `report --envelope - --candidate URI --sha256 H --runtime D`: the worker's output, which must be the envelope's intended output; the unit becomes `reported`. The first report of a profile pins its runtime digest for the run; a different digest later is refused.
- `verifications <run> --profile P` and `admit --verification - --report URI --sha256 H`: a verifier, a separate process, takes the reporting attempt's leases (renewed, or re-taken once lapsed), reads the destination and reports the step's checks; Bookkeeping checks every binding, the required checks and the live fence, then completes the unit (`finish`, `finish_resource` or `finish_expand`).
- `fail --envelope - --message M` gives an attempt up; `finalize <run>` delivers control's events and records the run's checks.
- Control's own checks (`input.hash`, `output.receipt`, `manifest.hash`, `work.accounting`, `journal.delivered`) are a fixed list in control. Every other check ID a step names must come back true in the verifier's report.
- Control emits only its lifecycle event (`work.verified`). Domain events go through the worker's own Journal intent.
- Migration `005` adds the state, two columns, `report()`, `verify_claim()` and the completion trigger, and drops `authorize_request()`; 001–004 stay as they are.

## What 20a takes down until 20c and 20e

`rules run --target mdm` (ticket 04's command), `bookkeeping prepare` and `mdm prepare-clean-company` stop working: their callbacks are deleted, and they come back as workers. Today they could only run through the coupled path, which #785 says not to use.

## Safety assertions to prove again

Each test file 20a deletes holds assertions a later slice must prove again on the new protocol, with the same meaning.

| Assertion | From | Proved again in |
|---|---|---|
| A fetch is authorized, and the Journal acknowledges it, before the request starts; a Journal outage blocks the request | `test_change_journal_acquisition_postgres::test_journal_outage_blocks_request_and_resume_reconciles_lost_ack` | 20c |
| A lost completion acknowledgement never refetches | `…acquisition…::test_lost_capture_completion_ack_does_not_refetch` | 20c |
| Capture is bounded by configuration only; unchanged links reuse verified bytes | `…acquisition…::test_bounded_family_capture_uses_configuration_only`, `test_conditional_unchanged_links_verified_bytes` | 20c |
| Invalid acquisition fails closed; producer counts must be exact integers | `…acquisition…::test_invalid_acquisition_fails_closed`, `test_direct_rules_proof_cannot_bypass_exact_integer_producer_accounting` | 20c |
| A resource checkpoint spans runs; compare-and-set rejects a stale completion; a hole and a takeover are atomic | `…acquisition…::test_resource_checkpoint_*` | 20a (control) |
| Restricted SQL functions reject missing fencing or completion evidence | `…acquisition…::test_restricted_sql_control_functions_reject_missing_fencing_or_completion_evidence` | 20a and 20b |
| Source manifests keep business evidence and the original Journal keys; missing evidence or authorization never succeeds; an empty scope needs an exact typed inventory; producer counts and business keys are read back; duplicate keys prove nothing | `test_change_journal_source_evidence_postgres` (all 10) | 20c |
| A revision's predecessor is a committed, acknowledged receipt; unsettled work in the same scope blocks the next revision | `…source_evidence…::test_revision_predecessor_*`, `test_unsettled_same_scope_work_blocks_next_revision` | 20c |
| A fresh Rules registration ingests, and a lost Journal acknowledgement is reconciled without a second write | `test_change_journal_mdm_postgres` | 20e |
| Preparation pins a bounded revision with no provider; Company routes with and without pagination | `test_company_only_postgres` | 20c |
| Planning makes no live change; validation executes; deployment needs the matching validation proof | `test_change_journal_skill_postgres` | 20c |
| A retired Rules version's run resumes from its original export and mapping | `test_configured_bookkeeping_postgres::test_retired_rules_resume_*` | 20e |
| A bounded `rules run --limit` leaves the rest pending, and a resume finishes it; `bookkeeping checks` shows every check true | `test_configured_bookkeeping_postgres::test_operator_cli_submits_and_resumes_frozen_work` | 20a in part (submit, resume and finalize in the two-worker test); the bounded worker limit with `--limit` in 20c |
| A real MDM commit keeps its hash and reconciles a lost acknowledgement; assessment writes reject expired authority; source ingest pins the mapping; platform publication fails and recovers | `test_configured_bookkeeping_postgres::test_actual_mdm_commit_*`, `test_assessment_writes_*`, `test_configured_source_ingest_*`, `test_configured_platform_publication_*`, `test_stage_manifest_chains_prepared_mdm_*` | 20e |
| Crash after the destination commit, before control, reconciles; the destination's transaction fence rejects expiry at commit | `test_configured_bookkeeping_postgres::test_crash_after_destination_*`, `test_destination_transaction_fence_*` | 20a (copy worker) and 20b |

## Slices

| Slice | What | PR |
|---|---|---|
| 20a | Control-only Bookkeeping: the task envelope and report, an external worker process, an architecture gate with domain packages blocked; delete the registry, `company.py`, `mdm_capabilities.py`, `source_input.py` and the `register_*` calls | |
| 20b | PostgreSQL 16 restricted-role and recovery gates (stale fence, wrong issuer or binding, forged checks, conflicting reports; lost acknowledgement, crash after commit, lease expiry during verification, missing runtime, Journal outage) | |
| 20c | SEC Company through the engine only: acquisition worker, Company reading from `rules/sources/sec.submissions.company` (absorbs ticket 17); delete the Company loaders and custom code | |
| 20d | Person through the engine only, from `rules/sources/sec.submissions.person`; delete the fixture conversion | |
| 20e | MDM worker and verifier (ingest, merge, publication) behind the protocol; `rules run --target mdm` cut over and proved end to end (ticket 04) | |

## Checklist

- [x] Read the design, `INDEPENDENCE.md` and Codex's ownership note; check Codex and Grok worktrees for Bookkeeping work (none; Codex is benchmarking the parser on `codex/rust-parser-review-20261002`). 2026-10-02 17:57 ET
- [x] Inventory the coupling: `cli.py` (acquisition, source evidence, Company, MDM, Journal publishers), `engine.py` (`acquisition_authority`, Journal branches, `authorize_request`), `source_input.py`, `mdm_capabilities.py`, `company.py`, `acquisition/capture.py`, `application/source_evidence.py`, `application/journal_evidence.py`, `application/journal_recovery.py`, `mdm/clean/cli.py`, `mdm/clean/company_source.py`, `rules/cli.py` (`configured_bookkeeping`, `book._run`); 9 integration test files. 2026-10-02 17:57 ET
- [x] GoF consult (above). 2026-10-02 17:57 ET
- [x] 20a: architecture gate: `tests/architecture/test_bookkeeping_control_only.py` starts control in a child process with `edgar`, `pyarrow`, `lxml`, `bs4`, `source_contract` and `edgar_warehouse.{mdm,loaders,parsers,serving,application,acquisition,silver_*,workers}` blocked, and builds every command (4 passed). Building the full CLI imported MDM, so `edgar-warehouse bookkeeping …` now builds only its own commands. 2026-10-02 18:20 ET
- [x] 20a: the task protocol: migration `005_task_protocol.sql` (state `reported`, `work_item.candidate`, `pipeline_run.runtimes`, `report()`, and a trigger that refuses any completion other than the reported candidate); engine `envelope`, `tasks`, `renew`, `report`, `fail`, `verifications`, `admit`; commands `claim`, `renew`, `report`, `fail`, `verifications`, `admit`, `finalize`. Tested: forged bindings and checks refused, runtime pinned, lost acknowledgements idempotent, populated-table migration. 2026-10-02 18:20 ET
- [x] 20a: workers `edgar_warehouse/workers` (`artifact.copy`, `jsonl.count`), each run with `python -m edgar_warehouse.workers work|verify`, reaching control only through the commands in a subprocess. `test_two_workers_in_their_own_processes_complete_a_cli_submitted_run` submits with `rules run`, runs both workers and verifiers as processes with control's domain imports blocked, and finalizes: complete, 4 verified, both runtimes pinned. 2026-10-02 18:20 ET
- [x] 20a: deleted `bookkeeping/clean/{capabilities,company,mdm_capabilities,source_input,runner}.py`, `edgar_warehouse/acquisition/`, `application/source_evidence.py`, the Journal operation branches and `authorize_request`; `journal_evidence` keeps planning only; `rules run` submits only; 5 test files retired (their assertions are in the table above); the control tests moved to the protocol. Local: Bookkeeping, generated-work and Journal Postgres tests 59 passed; unit, architecture and MDM tests 900 passed, 15 failed only because `jq` is not installed on this Mac since Homebrew was removed (CI has it). Skill and spec docs updated. 2026-10-02 18:20 ET
- [x] 20a: three-axis `/code-review`, findings fixed, each with a test. 2026-10-02 18:29 ET
  - **GoF:** leave the structure; the verification report's shape was written in two places, now one `report_document`.
  - **Standards, fixed:** a reported unit whose lease lapsed was handed to another worker and redone, and `verifications` applied its limit before the live-lease filter (now a reported unit belongs to verifiers, which re-take its lease: `verify_claim`); `authorize_request` stayed callable (dropped); run checks fell through to `journal.delivered`; `envelope` blocked the run from a read path (now only `tasks` blocks); the run row was locked on every report (only the first pin locks it); the renewal error was ignored and control calls had no timeout; the glossary lacked the new terms (`CONTEXT.md`).
  - **Spec, fixed:** a candidate could be reported anywhere (it must be the intended output); the envelope had no deadline; resource checkpoints and the restricted functions were not proved again (two tests); gate 1 claimed more than the tests show (now "Partly"); the protocol section used the design's command names; a deleted test had no row.
  - **Spec, moved to 20b:** a control-only wheel; a verifier profile and runtime of its own; retry limits in the envelope.
  - Local after the fixes: Bookkeeping, generated-work and Journal Postgres tests 59 passed; architecture and contract tests 46 passed.
- [x] 20a: PR #801, CI green (6 checks); merged on the operator's "agreed". 2026-10-02 22:20 ET
- [x] 20b: a control-only wheel (`packages/bookkeeping`, `edgar-bookkeeping`), installed in a clean environment with the Journal wheel and no domain distribution, runs migrate, grant-profile and a whole run through its own CLI in isolated mode on PostgreSQL 16 (`test_bookkeeping_wheel_postgres.py`, 2 passed). 2026-10-02 22:30 ET
- [x] 20b: issuer roles, migration `006_issuer_roles.sql`: `bk_worker_<profile>` and `bk_verifier_<profile>`, granted with `bookkeeping grant-profile`; `report` needs the worker role, `verify_claim`, `pin_verifier` and the completion trigger need the verifier role and a login other than the reporter's (`test_only_a_profiles_roles_*`). Control's grants now go to one runtime group; the worker and the verifier log in separately. 2026-10-02 22:30 ET
- [x] 20b: the verifier's runtime in its report, pinned as `verify:<profile>` (`test_a_verifier_runtime_is_pinned_for_the_run`). 2026-10-02 22:30 ET
- [x] 20b: retry limits in the envelope (`retry`, the claim's contention backoff). 2026-10-02 22:30 ET
- [x] 20b: a lease that lapses while a verifier runs: the late admission is refused (stale lease), a fresh verification re-takes it with a new token and completes the unit (`test_a_lease_lapsing_*`). 2026-10-02 22:30 ET
- [ ] ~~20b: destination re-verification on resume~~ moved to 20e: today's outputs are immutable files whose bytes control rechecks on resume; MDM is the first destination that can change after it is written
- [x] 20b: three-axis `/code-review`, findings fixed, each with a test. 2026-10-02 22:38 ET
  - **GoF:** leave the structure; the wheel listed each migration by hand, so a new one could ship missing (now the folder, and the test compares file sets).
  - **Spec, fixed:** claims were open to any control login, and a report or pin named its profile itself: now each run freezes its steps' profiles (`submission.profiles`), and `claim`, `heartbeat`, `wait_work`, `report`, `verify_claim`, `pin_verifier` and the completion trigger check the caller against that frozen profile; the verifying login is kept on the unit (`work_item.verifier`), its runtime in the report the receipt names.
  - **Standards, fixed:** a refused admission could still pin its verifier's runtime (now pinned in the completion's own transaction); long or look-alike profile names collided or exceeded 63 bytes (role names now carry a hash); no populated-table test for 006 (added, with a reported row); both wheels shipped `edgar_warehouse/__init__.py` and `control_contract.py` (now only the Journal wheel); S3 is the wheel's `s3` extra.
  - **Noted, not done:** `retry` in the envelope is the claim's contention backoff; capping a unit's work attempts is open (20c, where the first retried work arrives).
  - Local after the fixes: 107 passed (Bookkeeping, generated work, Journal, the wheel, architecture and contract tests).
- [x] 20b: PR #802; CI green (all six checks); merged on the operator's word "merge", 2026-10-02 22:42 ET
- [ ] 20c: SEC Company through the engine (expanded below by the operator's next request). Checked 2026-10-09 21:05 ET: `company.expand`, `company.silver`, `company.prepare`, and `company.publish_expand` are still declared in `rules/sources/sec.submissions.company/source.yaml` and are not registered worker profiles. Lookup of each returns `Unknown worker profile`. Registered profiles are `artifact.copy`, `jsonl.count`, `mdm.merge`, `mdm.prepare`, `mdm.publish`, `source.combine`, and `source.read`. The rules file was not renamed.

### Delete all legacy code and rewire using configuration

Operator, 2026-10-02 22:45 ET: "delete all legacy code and rewire using configuration".

Reading: every source is read from its rules file by the configured engine, and the hand-written readers behind it go. Order per source: a generic engine primitive, then the source's `read:` block, then equivalence on the pinned capture (same assertions, IDs, deferrals and refusals), then the delete, in the same PR. A difference from today's outputs is shown to the operator, never accepted silently. Each changed source version needs a test run and the operator's approval of its digest.

| Module | Fate |
|---|---|
| `infrastructure/edgartools_sec_gateway.py`, `filing_content_gateway.py` | Dead now (only tests import them): delete with their tests |
| `infrastructure/sec_client.py` | Kept until the configured capture worker (20c) replaces it; then deleted |
| `mdm/clean/company_source.py`, `loaders/`, the landing-parquet Company path | Replaced: Company read from the raw submissions JSON by its rules file, like Person |
| Worker profiles `company.expand`, `company.silver`, `company.prepare`, `company.publish_expand` | Renamed to generic profiles; no Company-named step |
| `mdm/clean/gleif_source.py` | Replaced: GLEIF on the engine (ticket 16), a later slice |
| `mdm/clean/adapters.py` record mapping | Replaced by the engine's reading once every source has a `read:` block |
| `silver_landing_store.py`, `silver_schema.py`, `serving/` | Out of this ticket: the dashboard imports `serving/`, and configured silver outputs are rules-skill ticket 05 |

- [x] L1: deleted `infrastructure/edgartools_sec_gateway.py` and `filing_content_gateway.py` (no importer outside one test), their two boundary tests, two boundary tests whose subject files were already gone (`object_storage.py`, `dataset_path_catalog.py`) and an empty Snowflake-publisher test, and `docs/capture-modes.md` (its `capture_mode` module was gone); `test_boundaries.py` and `test_sec_client.py` 11 passed. 2026-10-02 22:46 ET
- [x] L2: GoF consult: leave the structure. Each primitive is validated in `validate_expr` and evaluated in the value match, both in `lib.rs`, which has one commit. Parallel-array rows belong in a table's `each` (`items_of`), and grouping is a table option, not a column primitive; a lookup and a case are column primitives; `steps.py` is unchanged. 2026-10-02 22:46 ET
- [x] L3: engine primitives, each tested alone: parallel-array rows (SEC `filings.recent`), a reference-table lookup, classification as configuration, grouping by key. 89 passed in 9.09s on 2026-10-09 19:35 ET, engine build ae627570. `tests/engine/test_parallel_records.py`, `tests/engine/test_reference_lookup.py`, `tests/mdm/test_clean_classification.py`, and `tests/engine/test_source_combine.py`. The place-code lookup reads published RDM `sec-place-codes` version 1. The old `rules/reference/sec-place-codes.yaml` file is gone. L4 through L8 stay open.
- [ ] L4: Company `read:` block; equivalence on the pinned ticket 27 capture; delete `company_source.py` and `loaders/`; source version to the operator. The original 14 Company columns match the retained loader on 1,000 pinned submissions from that capture, checked 2026-10-09 19:46 ET. The current read also carries `last_sync_run_id` and `last_synced_at`. Deleting `company_source.py` and equivalence of the whole capture stay open. `loaders/` is already gone.
- [x] L5: Person `read:` block on the engine; equivalence; delete the fixture conversion (20d). `tests/engine/test_raw_submissions.py`: 17 passed in 4.86s on 2026-10-09 19:45 ET. 1,000 pinned submissions from the ticket 27 capture keep the complete Person record and the same governed outcome: 386 assertions, 447 `classification_entity_undetermined`, and 167 `classification_deferred`, in 51.74s on 2026-10-09 19:46 ET, engine build ae627570. `tests/mdm/test_fresh_mastering_cohort.py::test_removing_person_fixture_conversion_preserves_all_assertion_ids_and_provenance` passed in 0.95s and keeps assertion digest `35220d0129283863f957b93fee8317c4ce9ec390003d57d74d52e3709c29640c`. 20d stays open because it is blocked by 20c.
- [ ] L6: GLEIF `read:` block; equivalence; delete `gleif_source.py` (ticket 16). In-memory fixture behavior passed: `tests/mdm/test_clean_gleif_source.py`, 52 passed in 2.85s on 2026-10-09 20:37 ET. The golden-copy comparison and deletion stay open. `gleif_source.py` is still imported by `source_publications.py`, `native_consumption.py`, `company_source.py`, and `gleif_publication.py`.
- [ ] L7: delete `adapters.py` record mapping once no source needs it. Record mapping is still required, checked 2026-10-09 20:48 ET: `tests/mdm/test_clean_classification.py` passed 33 tests in 1.85s. Callers remain in `mdm_merge.py`, `name_census.py`, `cli.py`, `company_source.py`, `gleif_source.py`, `quality.py`, and `store.py`. The Name Frequency command in `cli.py` still calls `write_name_census`.
- [ ] L8: configured capture worker for `provider.capture`; delete `sec_client.py`. Checked 2026-10-09 20:50 ET: no worker under `edgar_warehouse/workers/` implements `provider.capture`. `tests/architecture/test_boundaries.py::BoundaryTests::test_httpx_only_lives_in_sec_client` passed in 0.16s, so `sec_client.py` remains the only HTTP client. The live SEC proof stays blocked on the operator's permission.
- [ ] 20d: Person through the engine
- [x] 20e: MDM behind the protocol; ticket 04's proof. `journal_delivery.py` does not read Bookkeeping's private `_frozen` or `_resolve_item`. Checked 2026-10-09 20:18 ET: the module names neither symbol and does not import Bookkeeping, and `JournalPublisher` refuses an origin that lacks a run, source, and feed. The worker passes that origin from the task envelope. The PostgreSQL protocol proof remains the 2026-10-03 record on issue 21 and was not repeated beside the archive verifier.
