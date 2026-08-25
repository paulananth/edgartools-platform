# 21 — Migrate submissions snapshots and pagination

**What to build:** Carry submissions main snapshots and every declared
pagination file through registered discovery, acquisition, completeness,
revision, and Silver-publication behavior as one source-family slice.

**Blocked by:** 17 — Make Bronze capture retry-safe and recoverable; 20 —
Version and activate the Acquisition Universe

**Status:** resolved

- [x] The family Strategy defines the company and pagination logical keys,
  ordered inventory proof, conditional fetch behavior, and required producers.
- [x] A main snapshot cannot declare completeness while a referenced pagination
  file is missing, deferred, failed, corrupt, or unverified.
- [x] Company, address, former-name, and submission-file scopes remain distinct
  and retire only from a proved complete scope.
- [x] Complete empty scopes, unchanged observations, pagination changes, and
  replay all reach explicit verified outcomes.
- [x] The acquisition Command registration bundles execution, scope resolution,
  and planned writes without adding source-family branches to the Facade.

## Answer

Added a `submissions` Source Family alongside `filing_artifact`:

- **Strategy** (`source_family_registry.py`): `SubmissionsPolicy` — fetches
  via `edgartools_sec_gateway.download_bytes` (a catalog-object gateway, not
  the filing-content one), completeness gated on `valid_json_object`. Wired
  into `_POLICY_FACTORIES` as `on_demand_fetch`, same acquisition_mode as
  `filing_artifact`.
- **Discovery** (`submissions_discovery.py`, new): a genuinely new two-phase
  shape — fetch+capture a CIK's main `submissions.json` through the Ticket
  14 ledger, parse it, discover N declared pagination file names, then
  issue and drive N more Fetch Decisions for those, all through the same
  ledger. `submissions_main_candidate_id(cik)` /
  `submissions_pagination_candidate_id(cik, file_name)` are keyed only by
  stable business identity (no run_id/universe_label), so replay performs
  zero duplicate network fetches — this was the one genuine bug caught
  during TDD (see below).
- **Silver acceptance** (`submissions_silver_acceptance.py`, new): seals
  `sec_company`/`sec_company_filing` as the required producers (configurable,
  gated by `UnsupportedRequiredProducers` against what this Strategy can
  actually serve). A main candidate's scopes (company/address/former-name/
  submission-file, via the existing `stage_submission`) are only retired and
  rewritten once `pagination_complete` is true for that CIK — an incomplete
  main candidate is *skipped*, not failed, so it retries cleanly next replay.
- **Command** (`drive-submissions-discovery`, registered in
  `acquisition_command_registry.py`): bundles execute/resolve_scope/
  planned_writes for a CIK-universe scope; `facade.py`'s `SourceFamilyPolicy`
  Protocol (fetch/is_complete only) is untouched — confirmed via an empty
  diff on that file.
- **Bootstrap**: `infra/scripts/bootstrap-source-family-registry.sh` now
  activates `filing_artifact` and `submissions` together in one registry
  draft (smoke-tested against real dockerized Postgres, fresh + idempotent
  re-run).

**Bug found and fixed via TDD, not review:** candidate IDs were originally
keyed by a run-derived `universe_label` (`f"{tracking_status_filter}:{run_id}"`),
which meant every invocation looked like a brand-new candidate to the ledger
— replay would re-fetch every CIK's submissions from SEC every single run.
Caught by a replay-safety test asserting `network_fetches` stays flat across
two full command invocations; fixed by dropping `universe_label` from both
ID functions entirely (kept only on the manifest's own digest/audit label,
which doesn't gate identity).

**Code review** (Standards + Spec axes, fixed point `origin/main`): Standards
found two real issues — a missing `UnsupportedRequiredProducers` gate (the
Ticket 32 pattern hadn't been ported to this sibling family — the exact
"sibling path silently diverged" shape CLAUDE.md already names) and two
Duplicated Code smells (revision-materialization logic repeated across the
two Silver finalize functions; decision-driving logic repeated across the
two discovery drive functions) — both fixed via extracted shared helpers.
Spec review verified the replay-safety and retire-gating behavior directly
against current source and found no missing/partial requirements, no scope
creep, and no incorrect implementations.

Full suite green: 2530 passed, 4 skipped. Committed as `0160e168` on
`claude/change-propagation-ticket21-migrate-submissions-pagination`; PR
pending.
