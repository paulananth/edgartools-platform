# Implement durable Daily-Artifact resume and disposition

Type: task
Status: claimed
Blocked by: (none — Decide a Durable Daily-Artifact Resume and Disposition Contract resolved)

## Goal

Implement the accepted run-bound daily-artifact manifest and append-only
per-accession outcome ledger so an interrupted daily run resumes only
outstanding work without weakening byte-exact immutable capture.

## Scope

1. Persist an immutable manifest binding run identity, ordered daily-index
   inputs, canonical accessions, warehouse image identity, and relevant
   parser/configuration versions before artifact processing.
2. Persist append-only, accession-scoped outcome records with the accepted
   disposition vocabulary and bounded candidate retry accounting.
3. Make the daily state-machine/task retry path resume from the original run
   manifest, selecting only pending, retryable, or explicitly
   repair-authorized candidates; completed candidates must never be refetched.
4. Add an operator repair-attestation flow for immutable-content conflicts.
   It must bind the candidate and conflict evidence to the original run and
   make replay explicit; it must not bypass the immutable-object guard.
5. Preserve the canonical Silver publication boundary: incomplete or
   unresolved manifests fail closed and cannot publish or satisfy the
   six-hour full-chain gate.

## Acceptance

- Focused tests prove manifest identity cannot drift on resume, completed
  candidates are skipped, and every original candidate is accounted for.
- Focused tests distinguish candidate transient retry, terminal repair, and
  task-infrastructure retry; unknown failures fail closed.
- Focused tests prove only a valid repair attestation authorizes a repaired
  candidate replay under the original run identity.
- Immutable-image production evidence demonstrates a controlled partial run,
  resume without refetching completed accessions, and fail-closed unresolved
  outcome behavior. It records manifest/ledger/attestation evidence without
  secrets.
- Schedule activation remains separately gated by full-chain evidence within
  six hours.

## Progress (2026-08-01)

Implemented the durable local/runtime contract:

- `daily_artifact_resume` writes an immutable run manifest bound to run id,
  image identity, exact daily-index accession union, and selected configured
  candidates; attempting to resume with changed identity fails closed.
- Immutable per-accession `succeeded` markers cause a same-run retry to skip
  completed artifact work. Immutable-content conflicts write a separate
  `terminal_repair_required` marker and remain excluded until a matching,
  immutable operator repair attestation supplies operator identity, repair
  action, and conflict evidence.
- The recurring artifact pipeline loads this durable disposition before work,
  writes terminal success/repair outcomes, and leaves unresolved repair work
  fail-closed. Existing local test doubles without a storage root retain their
  prior non-durable behavior; every deployed command context has the storage
  root and therefore uses the ledger.

Focused daily regressions: 171 passed. Repository-wide Ruff currently reports
pre-existing findings in `warehouse_orchestrator.py` (including unresolved
`_resolve_seed_limit` / `_resolve_seed_document` references); the new module
is clean. Remaining acceptance work is immutable-image deployment and a
controlled production partial/resume/repair-evidence run. Status remains
claimed until that evidence exists.

## Comments

### 2026-08-01 production observation — `daily-rc-81c0e04168fb-20260801T141043Z`

The immutable-image full-chain execution remained `RUNNING` at 13:54 EDT with
no Step Functions redrive. The bounded company-identity map completed in about
17 minutes, confirming the former repeated full-Silver publication loop is no
longer the dominant stage. The single `ReduceIdentityRefresh` publication still
took about 72 minutes.

The warehouse task entered Daily-Artifact with 5,097 configured candidates.
Its durable run state contained 494 immutable `succeeded` outcomes and one
`terminal_repair_required` outcome at 13:54 EDT, with no repair attestation.
The terminal outcome is the known byte-exact conflict for accession
`0000905148-26-003370`; the task continued processing later candidates rather
than losing completed work or immediately restarting the whole batch. This is
positive live evidence for per-accession disposition, but the execution must
still fail closed at publication while that terminal outcome is unresolved.

Observed artifact throughput was roughly 18 accessions per minute. At that
rate, artifact processing alone projects to roughly 4.7 hours; combined with
about 3.3 hours already spent before artifact processing, the six-hour
full-chain gate cannot be met by this execution even before downstream stages.
Keep this item claimed: completion still requires an explicit repair
attestation followed by a same-run retry proving the 494+ completed accessions
are skipped rather than refetched.
