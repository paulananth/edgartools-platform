# Auditor Evidence Ingestion Contract

## Decision

`AUDITED_BY` means **the principal registered public accounting firm that issued the audit report covering an issuer's annual financial statements**. It does not mean the currently appointed accountant and does not include every component audit participant.

The primary authority is the immutable SEC annual filing. Parse the direct filing's Inline XBRL auditor triplet whenever it is complete and valid; do not depend on the aggregated CompanyFacts endpoint. If the triplet is absent, parse the bounded independent-auditor report and signature section from the same filing. PCAOB AuditorSearch/Form AP bulk data supplies authoritative firm identity, amendments and structured corroboration from its effective period onward.

The SEC requires `AuditorName`, `AuditorFirmId` and `AuditorLocation` tags for Forms 10-K, 20-F and 40-F for the covered annual periods. [SEC auditor-tag announcement](https://www.sec.gov/newsroom/whats-new/osd-announcement-010722-taxonomy-compatibility) Extraction is capability-based rather than gated solely by a date: inspect direct iXBRL first, then use the report parser when a complete valid primary triplet is absent.

PCAOB AuditorSearch is public, sourced from Form AP filings, and offers a complete daily bulk download. [PCAOB AuditorSearch](https://pcaobus.org/resources/auditorsearch) Form AP is required for audit reports issued for public companies and provides the filing firm identity and amendment chain. [PCAOB Form AP](https://pcaobus.org/about/rules-rulemaking/rules/form-ap---auditor-reporting-of-certain-audit-participants)

## Candidate inventory

Every `10-K`, `10-K/A`, `10-KT`, `10-KT/A`, `20-F`, `20-F/A`, `40-F` and `40-F/A` accession accepted at or before the frozen watermark is a candidate. A base annual filing is presumed applicable; absent or ambiguous evidence is never silently `not_applicable`.

The inventory binds:

- CIK, accession, form, accepted/filed/report dates and complete attachment index;
- primary annual document and every audit-report artifact hash;
- direct iXBRL contexts/facts and parser version;
- exact PCAOB AuditorSearch snapshot URL, publication time, SHA-256, data dictionary and row digest;
- generation ID and Release Data Watermark.

Amendments are candidates so they can be classified as a revised audit report, byte-identical carry-forward, no audit-report change, or superseding evidence.

## Evidence parser and silver model

Add an append-only `sec_auditor_report_evidence` table containing:

- candidate accession, CIK, form, report date and audited period end;
- principal firm name, location and normalized PCAOB Firm ID;
- `evidence_source` (`sec_ixbrl`, `sec_auditor_report`, `pcaob_form_ap`);
- SEC raw-object URI/SHA-256 plus iXBRL QName/context or audit-report byte/DOM locator;
- PCAOB snapshot URI/SHA-256, Form Filing ID, original/amended filing IDs and latest flag;
- parser/normalizer/resolver versions and evidence fingerprint.

The iXBRL parser is XML-aware. It selects the undimensioned required/consolidated context matching the audited period and requires the name/location/firm-ID triplet to agree. The SEC XBRL guide defines AuditorFirmId as the PCAOB-assigned firm ID. [SEC EDGAR XBRL Guide](https://www.sec.gov/files/edgar/filer-information/specifications/xbrl-guide.pdf)

The fallback parser is deterministically bounded to “Report of Independent Registered Public Accounting Firm” or the supported foreign equivalent and its signature block. It does not use an LLM or unbounded fuzzy extraction. The report must identify the signing principal firm, report date and location. PCAOB AS 3101 requires the firm signature, location and report date. [PCAOB AS 3101](https://pcaobus.org/oversight/standards/auditing-standards/details/AS3101)

Incomplete triplets, multiple conflicting primary contexts, filing/report mismatches, multiple signing-principal candidates, or SEC/PCAOB firm-ID conflicts are quarantined.

## Firm identity

PCAOB Firm ID is canonical and normalized as a decimal string without presentation padding. Ingest the full PCAOB firm/AuditorSearch identity set and aliases; do not retain the present Big Four/Next Six-only lookup boundary.

When a new valid Firm ID appears, create a deterministic audit-firm entity keyed by `pcaob:firm:<id>`. Preserve historical names and locations as aliases. Pre-tag name/location evidence resolves only through a versioned PCAOB alias mapping. Fuzzy or multiple matches remain unresolved.

The current lookup-only behavior and skip in [`pipeline.py`](../../edgar_warehouse/mdm/pipeline.py) cannot satisfy this contract.

## Candidate outcomes

- `applicable_loaded`: one principal auditor resolves and the candidate binds to one eligible relationship version and evidence fingerprint;
- `not_applicable`: only an amendment proven to contain no audit-report change or a byte-identical carry-forward, using stable reason codes;
- `superseded`: a revised audit report or Form AP amendment replaces earlier evidence and names its successor;
- `unresolved`: missing raw artifact, missing firm identity, unsupported report structure or absent required evidence;
- `quarantined`: parser ambiguity, conflicting primary contexts, cross-source identity conflict or corrupt evidence;
- `retryable_failed`: bounded source-transport failure only.

A base annual filing cannot be `not_applicable`. GO requires zero missing, unresolved, quarantined and exhausted retryable candidates.

## Temporal derivation

Each applicable principal audit report creates one `AUDITED_BY` relationship version. `effective_from` is the audit report date—not January 1 of the fiscal year. The next principal audit report closes the prior current version while preserving history. Properties include audited period end, source accession, PCAOB Firm ID, Form AP Filing ID when present, report date and evidence fingerprint.

The current `sec_accounting_flag` path may remain a downstream analytical projection, but it is not release lineage because it lacks report-level raw locators and uses CompanyFacts aggregation. The current fiscal-year date logic in [`pipeline.py`](../../edgar_warehouse/mdm/pipeline.py) must be replaced.

## Entitlement, retry and repair

Both SEC EDGAR and PCAOB AuditorSearch are public sources. Preflight proves approved HTTPS access, expected data dictionary/schema, immutable storage access, snapshot freshness, complete candidate artifacts and no credential dependency.

SEC acquisition uses the existing declared identity, rate limiter and immutable cache. PCAOB bulk snapshots are captured once and reused. Timeout, connection reset, 429 and 5xx are transient with bounded exponential backoff/jitter. Missing index-declared filings, schema drift, identity conflict and parser ambiguity are operator-action failures.

Form AP may arrive after the annual filing. Direct SEC evidence can establish the edge before Form AP appears, but later corroboration must be scheduled through the applicable PCAOB deadline and any conflict blocks the next generation. It must never silently overwrite SEC evidence.

Repairs are bounded by accession or Form Filing ID, preserve all prior bytes/outcomes, bump the relevant parser or mapping version and publish only in a new generation.

## Completeness and parity

Release evidence proves candidate count equals terminal ledger count; every applicable candidate maps one-to-one to an eligible relationship version; all endpoint Firm IDs exist in the full audit-firm identity set; and a no-change rerun produces identical semantic digests and zero new identities.

Exact MDM/Neo4j parity compares issuer CIK, canonical audit-firm ID, report date, audited period end, source accession, evidence fingerprint and temporal bounds, with zero missing/extra/dangling or quarantined/superseded leakage. `valid_zero` is allowed only for a complete inventory that genuinely contains no applicable annual candidates.

## Ownership and acceptance

- Warehouse Ingestion Builder: annual accession inventory, SEC/PCAOB acquisition and immutable evidence.
- Fundamentals Parser Builder: iXBRL and bounded report-section parsers.
- MDM Builder: full PCAOB identity/alias model and temporal derivation.
- Graph Operator: frozen generation and exact parity.
- Release Owner: accepts only zero unresolved/quarantine and complete digest-bound evidence.

Named people are assigned in the Release Evidence Manifest; no owner is inferred from Git history.
