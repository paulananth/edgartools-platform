# Required Relationship Bulk-Load Completion Gate

## Outcome

This gate proves that every required source candidate for `EMPLOYED_BY` and `INSTITUTIONAL_HOLDS` has reached a deterministic terminal outcome at the Release Data Watermark. It does not pass because a workflow completed, a table is nonempty, or a sample produced graph edges.

The gate is decision-complete, but the current implementation does **not** pass it. Production GO remains blocked until tasks 16–20 in the release-readiness map are implemented and a production evidence artifact passes.

## Relationship semantics

`EMPLOYED_BY` means **Reported Executive Employment**: employment of a named executive or covered officer evidenced by SEC proxy compensation disclosure or a Form 8-K Item 5.02 appointment, departure, or covered compensatory event. It does not claim to enumerate every employee of an issuer. The SEC's current Form 8-K defines Item 5.02 around director/officer departures, elections or appointments, and compensatory arrangements ([SEC Form 8-K](https://www.sec.gov/file/form8-kpdf)).

`INSTITUTIONAL_HOLDS` means a manager-to-security position reported in the effective public Form 13F filing set for a quarter. Restatement amendments supersede the original filing; amendments adding holdings supplement it. Confidentially omitted positions are not asserted until they become public through a later amendment. SEC instructions require a Form 13F cover page, summary page, and information table and distinguish restatement from added-holdings amendments ([SEC Form 13F FAQ](https://www.sec.gov/rules-regulations/staff-guidance/division-investment-management-frequently-asked-questions/frequently-asked-questions-about-form-13f), [SEC Form 13F](https://www.sec.gov/files/form13f.pdf)).

## Source coverage boundary

Coverage is **document-type specific**. Do **not** apply one global start date to
every form. The authoritative lookback table and rationale live in
[relationship-source-coverage-by-document-type.md](./relationship-source-coverage-by-document-type.md).

Summary (ends at Release Data Watermark `W` unless noted):

| Family | Forms | Start (initial GO) |
| --- | --- | --- |
| **13F / institutional holdings** | `13F-HR`, `13F-HR/A` | Hard floor **`2013-05-20`** (SEC XML information-table era; [SEC Form 13F FAQ](https://www.sec.gov/rules-regulations/staff-guidance/division-investment-management-frequently-asked-questions/frequently-asked-questions-about-form-13f)). Product history may be longer only if it still respects this floor. |
| **Proxy / employment baseline** | `DEF 14A`, `DEF 14A/A`, `DEFA14A`, `PRE 14A` | Latest definitive proxy on or before `W` (always), plus proxies with filing date ≥ **`W − 5 years`** for declared history. |
| **Item 5.02 8-K** | `8-K`, `8-K/A` (Item 5.02 or ambiguous items) | Filing date ≥ **`W − 1 year`**. Older 8-Ks are out of scope for this gate’s bulk-load denominator. |

**Historical note:** An earlier draft treated `2013-05-20` as a single window for
all relationship sources. That date remains correct for **13F XML** only. It is
**not** a requirement to bulk-load every 8-K since 2013.

Current-at-watermark proof:

- For each company to which Reported Executive Employment applies, load the
  latest applicable definitive proxy on or before the watermark (baseline may
  predate the five-year proxy history band) and every relevant Item 5.02
  `8-K`/`8-K/A` with filing date in **`[W−1y, W]`** after that baseline through
  the watermark.
- For each Form 13F manager, load every `13F-HR` and `13F-HR/A` in every complete
  SEC quarterly index from the **13F window start** through the watermark,
  including amendments.

An 8-K is a source candidate when its item metadata contains Item 5.02 **and**
its filing date is inside the **1-year 8-K window**. If item metadata is missing
or ambiguous, it remains a candidate **only inside that same 1-year window** and
its primary document must be fetched and classified. An 8-K conclusively
identified as unrelated is not downloaded for this gate and receives a
metadata-backed `not_applicable` outcome. This avoids treating all historical
8-K earnings filings as employment evidence.

## Authoritative candidate inventories

The gate freezes two accession-level inventories into the Relationship Generation Snapshot.

### Reported Executive Employment inventory

The inventory contains (each row filtered by **that form’s** lookback):

- `DEF 14A`, `DEF 14A/A`, `DEFA14A`, and `PRE 14A` accessions for in-scope companies
  with filing date ≥ **`W − 5 years`**, plus the selected current-state proxy
  baseline even if older;
- `8-K` and `8-K/A` accessions declaring Item 5.02 with filing date ≥ **`W − 1 year`**;
- `8-K` and `8-K/A` accessions whose item metadata is absent or ambiguous with
  filing date ≥ **`W − 1 year`**;
- the selected current-state proxy baseline for each applicable company.

The inventory is derived from the complete `sec_company_filing` population for the release entity universe, reconciled to the frozen SEC index/submissions manifests. Accession number is the candidate identity.

### Institutional Holdings inventory

The inventory contains every `13F-HR` and `13F-HR/A` accession found in every SEC
quarterly index from the **13F window start** (default hard floor `2013-05-20`)
through the watermark, not only filings belonging to the existing company
universe. It includes a per-quarter index fingerprint and manager-CIK list.

The current helper is not sufficient for release evidence because it catches an index error, logs it, skips the quarter, and still returns a list ([build_13f_filer_list.py](../../edgar_warehouse/scripts/build_13f_filer_list.py#L31)). Release mode must fail closed when any expected quarter is missing.

## Bulk-Load Completion Ledger

Every candidate has one immutable ledger row bound to the release candidate, source window, watermark, parser version, and source-manifest fingerprint. A row records:

- relationship type, CIK, accession, form, filing/report dates, and source-index identity;
- candidate reason and applicability outcome;
- artifact paths, byte counts, and SHA-256 hashes;
- required attachment identities, including the primary document and 13F information table;
- fetch attempts, retry classifications, and any explicit repair invocation;
- parser name/version and row identity/content digests;
- MDM relationship-version identities or a stable no-edge reason;
- final status and timestamps.

Allowed terminal statuses are:

- `applicable_loaded`: required artifacts are hash-verified, parsing succeeded, and every derived silver row is bound to MDM versions;
- `not_applicable`: evidence proves the candidate does not express the relationship, using a stable reason code;
- `superseded`: an amendment contract identifies the effective replacement and preserves the superseded record as history.

`retryable_failed`, `quarantined`, `unresolved`, missing ledger rows, and circuit-breaker leftovers are nonterminal for GO and block the gate. A zero-row parse is not automatically `not_applicable`; it needs a form-specific reason and evidence.

## Hard checks

### 1. Candidate inventory

- Every expected SEC quarter and company submission manifest is present and fingerprinted.
- Inventory counts reconcile by form, year/quarter, CIK, and accession.
- Duplicate accession identities are zero.
- Every applicable company has a current-state proxy baseline or an evidenced `not_applicable` outcome.
- Every 13F filing-manager CIK is present in the MDM source-entity inventory; unresolved managers are zero.

### 2. Artifact capture

- Every candidate requiring content has its required immutable artifacts and matching hashes.
- `13F-HR` and `13F-HR/A` require the information table; the SEC treats the information table as a required part of the filing even when it is submitted as a separate XML attachment ([SEC Form 13F FAQ](https://www.sec.gov/rules-regulations/staff-guidance/division-investment-management-frequently-asked-questions/frequently-asked-questions-about-form-13f)).
- Missing primary documents, missing information tables, raw-object lookup failures, and read failures are explicit candidate failures.
- `candidate_count = applicable_loaded + not_applicable + superseded`; every other count is zero.

The current bulk selector excludes all Branch B forms because it admits only ownership and ADV forms ([warehouse_orchestrator.py](../../edgar_warehouse/application/warehouse_orchestrator.py#L1848)). Historical dev evidence found only 23 of 52,200 proxy-family filings and none of 48,877 13F filings had attachment rows at that checkpoint ([phase 06 disposition](../../.planning/workstreams/fix-pipelines/phases/06-relationship-investigation-and-population/06-04-EDGE09-EDGE11-DISPOSITION.md)). Those historical counts are sizing evidence only and must be refreshed for production.

### 3. Parsing and silver publication

- Each candidate receives a per-accession parser outcome; aggregate `filings_skipped` is forbidden as release evidence.
- Proxy parsing produces identified executive rows or a stable evidenced no-record outcome.
- Item 5.02 parsing produces appointment/departure/role-change events or a stable no-employment-event outcome.
- 13F parsing applies restatement/addition semantics and proves the effective holding set per manager and quarter.
- Silver primary keys are unique and semantic row digests are stable on rerun.
- Parent filing foreign keys and artifact lineage are complete.

The present per-filing code silently increments `filings_skipped` for missing artifacts and continues ([fundamentals_ingest.py](../../edgar_warehouse/application/workflows/fundamentals_ingest.py#L105)); the 13F path behaves similarly ([fundamentals_ingest.py](../../edgar_warehouse/application/workflows/fundamentals_ingest.py#L293)). These paths require accession-level dispositions before they can satisfy the gate.

### 4. Workflow behavior

- The release bulk-load execution is fail-closed. Branch B exceptions cannot be caught and routed onward to MDM.
- The artifact circuit breaker stops new SEC requests but marks every unattempted candidate unresolved and fails the execution.
- No candidate, source row, derivation, graph sync, or verification cap is allowed in release mode.

The current load-history definition catches Branch B failures and continues to MDM ([deploy-aws-application.sh](../../infra/scripts/deploy-aws-application.sh#L1700)), and the operator sync script caps `INSTITUTIONAL_HOLDS` plus graph publication ([full-universe-sync.sh](../../scripts/ops/full-universe-sync.sh#L200)). Those modes cannot produce release evidence.

### 5. MDM applicability and derivation

- Every parsed executive/Item 5.02 event maps to exactly one company and person, or remains an unresolved blocker.
- Every effective 13F holding maps to exactly one manager entity and security; unresolved manager/security counts are zero.
- Every applicable ledger row binds to the exact MDM relationship-version identities created or updated from it.
- Departures close prior `EMPLOYED_BY` temporal versions; appointments open new versions.
- Restated 13F filings supersede the prior quarter set; added-holdings amendments supplement it without duplicating unchanged holdings.
- A no-limit idempotency rerun produces zero new relationship identities and identical semantic digests.

Current `EMPLOYED_BY` derivation reads only proxy compensation rows and creates one person-company-year edge ([pipeline.py](../../edgar_warehouse/mdm/pipeline.py#L1119)); it does not process Item 5.02 departures or appointments. Current `INSTITUTIONAL_HOLDS` derivation requires an existing adviser CIK and otherwise skips the row ([pipeline.py](../../edgar_warehouse/mdm/pipeline.py#L1335)). Both are implementation blockers.

### 6. Graph proof

For both relationship types, the frozen MDM set and hosted graph must pass the already-approved Per-Type Exact Relationship Parity contract: equal counts, identities, canonical properties, temporal fields, endpoints, and current-at-watermark subset, with zero missing, extra, inactive, quarantined, superseded, or dangling records.

## Retry and repair policy

- Normal reruns are idempotent: verified immutable artifacts are cache hits and are not fetched again.
- Only failures classified as transient may retry, with bounded attempts and backoff recorded per accession.
- Parser defects, missing required attachments, index gaps, unresolved identities, schema mismatches, and unknown failures fail closed for operator action.
- `--force` is permitted only for an explicit repair manifest naming accessions and reason codes. Evidence records the prior hashes, replacement hashes, operator, and approval. It is never the default bulk-load behavior.
- After any repair, rerun the affected candidate slice, its full relationship derivation, exact graph parity, and the final complete-ledger reconciliation at the unchanged watermark.

### Strict bulk-load resume (Ticket 20)

See [ticket20-strict-bulk-load-resume.md](./ticket20-strict-bulk-load-resume.md) for the operator path:

- **P0** batch_done markers + remaining CIK batches JSONL
- **P1** accession_done markers + skip terminal candidates on the same freeze
- **P2** mid-batch artifact progress logs
- **P3** never redrive after image/task-definition deploy; always a new execution

## Required evidence artifact

The run emits one secret-safe `required_relationship_bulk_load_evidence.json` containing:

- release candidate, image digests, coverage window, watermark, and snapshot fingerprint;
- source-manifest and candidate-inventory counts/digests;
- terminal-status counts and digest of the full Bulk-Load Completion Ledger;
- artifact, parser, silver, MDM, idempotency, and graph-parity check results;
- retry, circuit-breaker, quarantine, unresolved, and force-repair counts;
- execution identifiers and named Gate Attestations.

PASS requires every hard check to be present and successful, with no skipped check and all failure/unresolved counts equal to zero.

## Ownership

- **Warehouse Ingestion Builder** owns strict candidate enumeration, artifact capture, parser outcomes, silver lineage, and the completion-ledger implementation.
- **MDM Builder** owns entity resolution, temporal derivation, amendment semantics, and MDM idempotency evidence.
- **Graph Operator** owns hosted publication and per-type exact parity evidence.
- **Release Data Operator** executes the production bulk load and repair manifests.
- **Release Owner** accepts the gate only after named people fill all four operational roles in the Release Evidence Manifest.

No individual is inferred from Git history; unassigned named ownership remains a pre-execution blocker.

## Implementation sequence

1. Implement the strict source-candidate inventory and Bulk-Load Completion Ledger.
2. Implement manifest-driven Branch B artifact capture and fail-closed release workflow behavior.
3. Add Item 5.02 employment-event parsing and temporal `EMPLOYED_BY` derivation.
4. Complete the 13F manager universe and amendment-effective holding semantics.
5. Execute the production bulk load without caps, repair all unresolved candidates, and commit the passing evidence artifact.

