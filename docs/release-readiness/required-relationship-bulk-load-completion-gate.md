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

| Family | Forms | Start (initial agent GO) |
| --- | --- | --- |
| **13F / institutional holdings** | `13F-HR`, `13F-HR/A` | **`max(W − 3 years, 2013-05-20)`**. Hard floor **`2013-05-20`** is XML-era only ([SEC Form 13F FAQ](https://www.sec.gov/rules-regulations/staff-guidance/division-investment-management-frequently-asked-questions/frequently-asked-questions-about-form-13f)); full XML-era archive is Explore backfill, not first agent GO. |
| **Proxy / employment baseline** | `DEF 14A`, `DEF 14A/A`, `DEFA14A`, `PRE 14A` | Filing date ≥ **`W − 5 years`** only; baseline = latest definitive proxy **in band**. **No** pre–W−5y baseline exception. |
| **Item 5.02 8-K** | `8-K`, `8-K/A` (Item 5.02 or ambiguous items) | Filing date ≥ **`W − 2 years`**. Older 8-Ks are out of scope for this gate’s bulk-load denominator (Explore-only). |

**Historical note:** An earlier draft treated `2013-05-20` as a single window for
all relationship sources. That date remains correct for **13F XML** only. It is
**not** a requirement to bulk-load every 8-K since 2013.

Current-at-watermark proof:

- For each company to which Reported Executive Employment applies, load
  definitive proxies with filing date in **`[W−5y, W]`** (baseline = latest in
  band if any; if none, baseline is missing — not filled by older proxies) and
  every relevant Item 5.02 `8-K`/`8-K/A` with filing date in **`[W−2y, W]`**.
- For each Form 13F manager, load every `13F-HR` and `13F-HR/A` in every complete
  SEC quarterly index from the **13F agent window start**
  (`max(W−3y, 2013-05-20)`) through the watermark, including amendments.

An 8-K is a source candidate when its item metadata contains Item 5.02 **and**
its filing date is inside the **2-year 8-K window**. If item metadata is missing
or ambiguous, it remains a candidate **only inside that same 2-year window** and
its primary document must be fetched and classified. An 8-K conclusively
identified as unrelated is not downloaded for this gate and receives a
metadata-backed `not_applicable` outcome. This avoids treating all historical
8-K earnings filings as employment evidence.

## Authoritative candidate inventories

The gate freezes two accession-level inventories into the Relationship Generation Snapshot.

### Reported Executive Employment inventory

The inventory contains (each row filtered by **that form’s** lookback):

- `DEF 14A`, `DEF 14A/A`, `DEFA14A`, and `PRE 14A` accessions for in-scope companies
  with filing date ≥ **`W − 5 years`** (baseline = latest in band only; no older
  baseline exception);
- `8-K` and `8-K/A` accessions declaring Item 5.02 with filing date ≥ **`W − 2 years`**;
- `8-K` and `8-K/A` accessions whose item metadata is absent or ambiguous with
  filing date ≥ **`W − 2 years`**.

The inventory is derived from the complete `sec_company_filing` population for the release entity universe, reconciled to the frozen SEC index/submissions manifests. Accession number is the candidate identity.

### Institutional Holdings inventory

The inventory contains every `13F-HR` and `13F-HR/A` accession found in every SEC
quarterly index from the **13F agent window start**
(`max(W − 3 years, 2013-05-20)`) through the watermark, not only filings
belonging to the existing company universe. It includes a per-quarter index
fingerprint and manager-CIK list.

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

`EMPLOYED_BY` derivation applies proxy compensation baselines and then Item 5.02
employment events (appointments / departures / role changes) from
`sec_employment_event` ([pipeline.py](../../edgar_warehouse/mdm/pipeline.py)
`_derive_employed_by`). `INSTITUTIONAL_HOLDS` derivation still requires a
resolvable manager entity; unresolved managers remain fail-closed ledger
blockers rather than silent graph edges.

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

PASS requires every hard check to be present and successful, with no skipped
check, and all failure/unresolved counts equal to zero — **except** the
Item 5.02 8-K `unresolved` count specifically, which the Release Owner may
accept up to an explicit, enumerated bounded threshold (see "Accepted Item
5.02 unresolved exception" below). 13F and proxy/DEF 14A candidates carry
no such exception and must still reconcile to exactly zero
failure/unresolved/quarantine/circuit-breaker-leftover/unapproved-force —
confirmed architecturally clean of the "unresolved" failure mode entirely
(13F parses structured XML; the proxy parser returns empty rows rather than
an ambiguous outcome). Only Item 5.02's NLP-based extraction produces a
genuine `unresolved` applicability.

### Accepted Item 5.02 unresolved exception (2026-07-19, Release Owner decision)

The Item 5.02 parser's spaCy-based extraction cannot yet resolve every
required candidate — a real, measured gap, not an infra defect. A
400-then-2,000-sample scope check (0 fetch errors) found ~9.5% of Item
5.02 8-K candidates unresolved even after landing two safe, purely-additive
parser fixes (bulleted-roster segmentation, bare object-predicate roles,
`promoted to [Role]`); the remaining patterns (backward-references to
prior filings, biographical background prose, appositive names, nominalized
appointments under a different governing verb) are suppression-shaped
fixes that risk silently dropping real events rather than merely failing
loudly, so they were not rushed through. Confirmed concretely on a real
accession (GridAI Technologies, `0001104659-25-124213`) that the unresolved
bucket contains at least one genuine, currently-unextracted appointment.

**Insider-scoping decision (2026-07-19, Ticket 21):** the Release Owner
subsequently scoped EMPLOYED_BY completeness to **insiders** — people
appearing as reporting owners in Form 3/4/5 filings
(`sec_ownership_reporting_owner`). PASS additionally requires an
`insider_coverage` evidence block with **zero unresolved insiders** (every
observed insider resolves to one MDM person carrying an `IS_INSIDER`
version; `mdm verify-insider-coverage`, fail-closed). Unresolved Item 5.02
events cannot conceal an unidentified insider because insiders
self-identify through their own ownership filings. 13F/INSTITUTIONAL_HOLDS
checks are verified and reported but are non-blocking for the launch
decision per the same decision.

**Decision:** the Release Owner accepted this as a known, bounded gap
rather than requiring either full per-accession manual review (~570–750
filings, not practical) or further indefinite parser patching before GO.
**This means EMPLOYED_BY is NOT bulk-load complete** for the Item 5.02
family — the PASS phrase below says so explicitly rather than overclaiming
completeness. Implementation of the actual gate mechanism (evidence
schema field enumerating the accepted-unresolved accession list, the
specific numeric threshold, and preserving fail-closed behavior for any
unresolved candidate outside that pre-audited set) is **pending, not yet
built** — this section records the policy decision the mechanism must
implement, not a shipped capability.

## PASS / GO claim language (wayfinder ticket 13)

PASS means **agent-window bulk-load complete for 13F and proxy/EMPLOYED_BY
baseline sources, and complete except for an enumerated, Release-Owner-
accepted set of unresolved Item 5.02 candidates**, for frozen Ticket 20
candidates only — not full SEC history, not Form 3/4/5, not CAGR/financial
features, and explicitly **not** a claim that every Item 5.02 employment
event has been captured.

Every PASS evidence statement must bind:

1. inventory **fingerprint**
2. Release Data **watermark** `W`
3. **`coverage_by_document_type`** (13F / proxy / Item 5.02 8-K windows)
4. the **accepted Item 5.02 unresolved count/percentage**, if any, and a
   pointer to the enumerated accession list in evidence

**Approved Ticket 20 PASS phrase:**

```text
Required relationship sources for INSTITUTIONAL_HOLDS and the proxy/DEF 14A
EMPLOYED_BY baseline are bulk-load complete for agent windows at watermark W
(fingerprint F):
  13F [max(W−3y, 2013-05-20), W];
  proxy [W−5y, W] (latest-in-band baseline only).
Item 5.02 / ambiguous 8-K EMPLOYED_BY sources [W−2y, W] are complete except
for N enumerated unresolved candidates (X% of the Item 5.02 8-K candidate
inventory), accepted by the Release Owner as a known, bounded gap per
required-relationship-bulk-load-completion-gate.md — not claimed complete.
```

**Forbidden overclaims** (never on PASS/GO, Agent View, or evidence headers):
“complete since 2013” / “full history” for all relationship forms; “all 8-Ks
loaded”; “all proxies since IPO/2013”; “13F complete for full XML era” when the
freeze is only the agent 3y window; “EMPLOYED_BY enumerates every employee”;
Form 3/4/5 or CAGR completeness as Ticket 20; treating top-level
`coverage_start` as agent coverage for every form; Explore archive complete =
agent GO; **claiming Item 5.02 / EMPLOYED_BY "bulk-load complete" without
naming the accepted unresolved count** once the accepted-exception mechanism
is in use.

Full phrase pack: [agent-and-research-source-relevance-windows.md](./agent-and-research-source-relevance-windows.md)
and `.scratch/artifact-usefulness-timelines/issues/13-go-claim-language-for-partial-history.md`.

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

