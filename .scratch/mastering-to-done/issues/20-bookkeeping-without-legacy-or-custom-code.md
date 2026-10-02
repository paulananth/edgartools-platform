# Bookkeeping without legacy or custom code for Company and Person

Type: task (code), several PRs
Status: in progress (Claude, branch `claude/bookkeeping-independent`)
Blocked by: none for 20a and 20b; 20c needs 15 (done); 20d needs 20c
Blocks: 04 (the end-to-end `rules run` proof), 06 (the source switch-ons), 12, 17 (absorbed into 20c)

## Request

Operator, 2026-10-02 17:51 ET: "fix bookkeeping no legacy or custom code for company and person".

This is the explicit instruction that Codex's design ticket (`.planning/workstreams/bookkeeping-loader-independent-design/TICKET.md`) waits for before Claude implements. The design is `docs/research/bookkeeping-loader-independent-design-2026-10-02.md`, and the acceptance gates are in `skills/bookkeeping/INDEPENDENCE.md`.

## What the words decide

- **No legacy:** Company and Person workers do not wrap `bookkeeping/clean/company.py`, `stage_company_loader`, `company_source.py` or the Person fixture conversion. The design allowed today's loaders inside external workers; the operator's words rule that out for Company and Person.
- **No custom code:** Company and Person are read by the configured engine (ticket 15) from their rules files. Where the engine can't state something (individual-filer classification, address conversion, filing-array expansion, Company grouping), the engine gets a generic primitive, tested on its own. A Company- or Person-named Python step is not the fallback. This narrows ticket 08's "a custom step as the last resort" for these two kinds.
- **Bookkeeping is control only:** no domain imports, no callback registry, no branches on operation names (GoF consult, 2026-10-02 17:57 ET: remove the `Registry`/`Capability` layer and the Journal operation branches; keep the SQL lifecycle and migrations).

## Not changed by this ticket

- Zero SEC requests still holds. Removing the coupled path lifts the #785 blocker on ticket 06, but the SEC Company acquisition proof still needs a real fetch, on the operator's permission.
- No "independent" claim until gates 1–4 of `INDEPENDENCE.md` have run.

## The protocol (20a), pull not push

Workers pull work through `edgar-warehouse bookkeeping …` commands that print JSON; Bookkeeping spawns nothing and names no worker module.

- `submit`: freeze the approved Rules export and the input manifest (today's `start`).
- `claim --run R --profile P --limit N`: hand out task envelopes (run, step, key, attempt, fence, the resolved input reference, the Rules digest, the intended output, the effect key, the deadline). The step's `operation` names the worker profile.
- `renew --envelope E`: renew the lease while the worker runs.
- `report --envelope E --candidate URI --sha256 H --runtime D`: the worker reports its candidate; the item becomes `reported`. The first admitted report pins the profile's runtime digest for the run; a different digest later blocks.
- `verify-claim --run R --limit N` and `verify-report --verification V --report URI --sha256 H`: a separate verifier process reads the destination and reports the required check IDs; Bookkeeping checks every binding, the required checks and the live fence, then completes the work (`finish`, `finish_resource` or `finish_expand`).
- Control's own checks (`input.hash`, `output.receipt`, `manifest.hash`, `work.accounting`, `journal.delivered`) are a fixed list in control. Every other check ID a step names must come back true in the verifier's report.
- Control emits only its lifecycle event (`work.verified`). Domain events go through the worker's own Journal intent.
- New tables and functions come in migration `005`; 001–004 stay as they are.

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
- [ ] 20a: architecture test, red: start the Bookkeeping CLI and a control lifecycle with `edgar_warehouse.{loaders,parsers,silver*,mdm,acquisition,application,serving}`, `edgar` and `pyarrow` blocked
- [ ] 20a: the task envelope and report (schema, admission against bindings and the live fence)
- [ ] 20a: the worker process: `artifact.copy`, plus a second generic worker, with no Bookkeeping edits between them
- [ ] 20a: delete the callback layer and domain modules; move or retire their tests; the architecture test goes green
- [ ] 20a: three-axis `/code-review`; PR; CI green; merge on the operator's word
- [ ] 20b: the PostgreSQL 16 gates
- [ ] 20c: SEC Company through the engine
- [ ] 20d: Person through the engine
- [ ] 20e: MDM behind the protocol; ticket 04's proof
