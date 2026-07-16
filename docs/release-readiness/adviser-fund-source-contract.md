# Adviser–Fund Source Contract

## Decision

`MANAGES_FUND` means that an adviser reports that it advises, sponsors, or manages a private fund in Form ADV Part 1A Schedule D, Section 7.B. The authoritative release source is the public SEC/IAPD historical Form ADV Part 1 bulk filing data. The current Investment Adviser compilation is a separate completeness control for the active adviser universe and latest filing identity; it is not a substitute for the Schedule D private-fund tables.

The public bulk files require no IARD login or paid entitlement. Production therefore uses public HTTPS acquisition only. Undocumented IAPD search endpoints, screen scraping, EDGAR, operator-supplied PDFs, and the reduced monthly spreadsheet are not approved release sources.

The SEC publishes historical Part 1 filing data, including schedules, for SEC-registered advisers and exempt reporting advisers, and notes that multiple tables must be linked for use. It also warns that the files are posted about one month after quarter end. The Release Data Watermark must therefore identify the exact published ADV snapshot; it cannot claim same-day IARD currency. [SEC/IAPD Form ADV data](https://adviserinfo.sec.gov/adv)

The active-universe control is the official current compilation of investment-adviser firms registered with the SEC and state regulators. [IAPD investment-adviser compilation](https://adviserinfo.sec.gov/compilations)

## Regulatory and identity basis

Form ADV requires a Section 7.B.(1) report for each private fund an adviser reports, subject to the form's master-feeder and related-adviser instructions. When another SEC adviser reports the detailed fund record, the adviser uses Section 7.B.(2), so both sections are required to prove every adviser-to-fund edge. [Form ADV Part 1A](https://www.sec.gov/about/forms/formadv-part1a.pdf)

The private-fund identification number is the canonical fund source identity. The instructions require reuse of an existing private-fund ID rather than minting a new one, including across advisers and amendments. [Form ADV instructions](https://www.sec.gov/about/forms/formadv-instructions.pdf)

## Watermark and candidate inventory

The ADV component of the Release Data Watermark contains:

- official snapshot name, publication timestamp, URL, byte count, SHA-256 and schema/data-dictionary fingerprint;
- latest current-compilation snapshot with the same immutable metadata;
- every required source-table name, row count and deterministic content digest;
- the maximum filing date represented, plus the known publication-lag boundary;
- parser, normalizer and resolver versions.

The inventory includes every accepted Part 1 filing represented in the chosen bulk snapshot and every adviser in the current compilation. It reconciles the current compilation's CRD numbers and latest filing IDs to the filing tables. Missing source tables, duplicate filing identities, missing latest filings, or a snapshot advertised but not yet complete fail closed.

One relationship candidate is identified by:

```text
(filing_id, adviser_crd_number, private_fund_id, schedule_section, row_ordinal)
```

Section 7.B.(1) supplies the detailed private-fund identity and sponsor/manager fields. Section 7.B.(2) supplies a reporting adviser that relies on another adviser for the detailed fund record. Master and feeder funds retain their separate private-fund IDs; the parser must not collapse the arrangement into a name-only identity.

## Applicability ledger

Every candidate receives exactly one outcome:

- `applicable_loaded`: one adviser and one private fund resolve, and the candidate binds to one relationship version;
- `not_applicable`: stable source evidence says Item 7.B is `No`, the filing is not a Part 1 filing carrying the section, or a deleted record is no longer effective;
- `superseded`: a later filing/amendment replaces the candidate and names the successor filing;
- `unresolved`: missing PFID, missing detailed cross-reference, unresolved CRD, ambiguous master-feeder mapping, or a current-compilation/latest-filing mismatch;
- `quarantined`: duplicate PFID with contradictory legal identity, corrupt archive, schema drift, or contradictory effective rows;
- `retryable_failed`: bounded public-source network failure only.

GO requires zero missing, unresolved, quarantined, exhausted retryable, or silently skipped candidates.

## Parsing, normalization and effective set

- Parse the published relational CSV tables by their documented keys; do not reuse the current heuristic HTML/XML parser in [`adv.py`](../../edgar_warehouse/parsers/adv.py).
- Preserve the raw archive and every member file before parsing.
- Normalize CRD and PFID as strings without presentation padding. Preserve raw legal names, jurisdictions and fund types alongside versioned comparison keys.
- Resolve an adviser by CRD first, SEC file number second. Name-only matching never auto-accepts.
- Resolve a fund by PFID. A deterministic PFID-backed MDM fund is created when absent; fund name is an alias, not identity.
- Select the latest effective filing at or before the ADV watermark. Add/amend/delete actions version the source row. Deleted funds close the reported relationship; they are never physically removed from history.
- Where several advisers report the same PFID, retain every applicable adviser-to-fund relationship. Do not invent exclusivity.

The present silver schema drops PFID and action/cross-reference fields and caps extracted funds at 100 in [`adv.py`](../../edgar_warehouse/parsers/adv.py). Release implementation must remove that cap and add the missing lineage fields before using [`sec_adv_private_fund`](../../edgar_warehouse/silver_store.py) as release evidence.

## Entitlement and acquisition preflight

Before capture, the release runtime must prove:

1. DNS/TLS and public HTTPS access to the approved `adviserinfo.sec.gov` assets;
2. no login, session cookie, IARD credential, or undocumented API is required;
3. the expected snapshot and every required table are present;
4. response content type, archive integrity, data dictionary and schema fingerprint match an approved version;
5. publication date and maximum represented filing date satisfy the frozen ADV watermark;
6. sufficient immutable S3 space and KMS write access exist for the raw snapshot;
7. current-compilation CRD/latest-filing reconciliation completes before parsing.

Any failure is `operator_action_required`; the workflow must not fall through to MDM.

## Retry, repair and evidence

Only timeout, connection reset, HTTP 429 and HTTP 5xx are transient. Use bounded exponential backoff with jitter and honor `Retry-After`. Authentication responses, missing files, schema drift, archive corruption, duplicate keys, and reconciliation gaps fail closed without generic retry.

Normal reruns are SHA-256 cache hits and make no network request. `--force` requires a bounded repair manifest naming snapshot/files and reason. Repairs retain prior bytes and outcomes and create a new evidence version.

Release evidence records source-table counts and digests, current-compilation reconciliation, PFID/CRD uniqueness, terminal ledger counts, MDM relationship-version IDs, idempotent rerun digests, and exact MDM-to-hosted-graph parity for `MANAGES_FUND`.

## Graph contract

Each effective candidate produces:

```text
(Adviser)-[:MANAGES_FUND {
  private_fund_id,
  source_filing_id,
  source_section,
  valid_from,
  valid_to,
  evidence_fingerprint
}]->(Fund)
```

This keeps the PFID on the graph-facing relationship because it is easy to query and directly ties the edge to its regulatory identity. Exact parity compares canonical endpoint IDs, PFID, effective dates, source filing and evidence fingerprint; counts alone cannot pass.

## Ownership and acceptance

- Release Data Operator: official snapshot acquisition and entitlement preflight.
- Warehouse Ingestion Builder: relational parser, immutable lineage and completion ledger.
- MDM Builder: CRD/PFID entities, effective versions and idempotency.
- Graph Operator: generation publication and exact parity.
- Release Owner: accepts the snapshot lag, zero-unresolved ledger, evidence digest and named attestations.

Named people are assigned in the Release Evidence Manifest; no identity is inferred from Git history.
