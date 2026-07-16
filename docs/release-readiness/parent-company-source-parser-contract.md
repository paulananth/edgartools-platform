# Parent-Company Source and Parser Contract

## Decision and semantic boundary

For this source, `HAS_PARENT_COMPANY` means **a subsidiary disclosed by an annual-report registrant points to that filing registrant**. It does not claim the registrant is the subsidiary's immediate legal parent. Exhibit 21 generally provides a registrant roster, not the intermediate ownership chain, so indentation or table order must never create inferred hierarchy.

The graph edge carries `parent_scope = "registrant_disclosed"` and `immediate_parent_known = false` unless the source explicitly names an immediate parent. This preserves an easy-to-query Neo4j relationship without overstating the evidence.

Completeness means complete public SEC disclosure accepted at or before the Release Data Watermark, not every real-world subsidiary. Regulation S-K permits omission of collectively insignificant subsidiaries. [17 CFR 229.601(b)(21)](https://www.ecfr.gov/current/title-17/chapter-II/part-229/subpart-229.600/section-229.601)

Domestic filers use Exhibit 21. Form 20-F filers use Exhibit 8, whose instructions impose the corresponding subsidiary-list requirement. [SEC Form 20-F](https://www.sec.gov/files/form20-f.pdf) A 40-F registrant without an approved authoritative attached annual-report source remains unresolved and blocks GO; it is not silently classified `not_applicable`.

## Authoritative inventory

The source is the immutable SEC filing submission and its complete attachment index. SEC indexes and public filing directories expose accession identity and every submitted document, and accepted accession numbers are unique. [SEC access to EDGAR data](https://www.sec.gov/search-filings/edgar-search-assistance/accessing-edgar-data)

The generation-bound inventory has three levels:

1. **Registrant-period candidates:** every release-universe company joined to complete submissions history through the watermark, including submission overflow files.
2. **Filing candidates:** every `10-K`, `10-K/A`, `10-KT`, `10-KT/A`, `20-F` and `20-F/A`, plus any filing referenced by an incorporated subsidiary list.
3. **Document/row candidates:** every `EX-21*` domestic exhibit, `EX-8*` Form 20-F exhibit, incorporated-reference target, parsed subsidiary row, explicit no-subsidiary statement and explicit omission statement.

The current snapshot uses the latest effective annual disclosure chain at or before the watermark. An amendment supersedes only the exhibit/material it actually replaces. Missing incorporated references, cycles, unexplained missing exhibits and unsupported 40-F sources are unresolved blockers.

Inventory fingerprint inputs are registrant IDs, accession/form/accepted/report dates, full attachment index, incorporated-reference chain, artifact hashes, parser/normalizer/resolver versions and generation/watermark IDs.

## Parser contract

Select documents primarily from normalized EDGAR document type:

```text
^EX-21(?:\..+)?$   domestic Item 601 subsidiary list
^EX-8(?:\..+)?$    Form 20-F subsidiary list
```

Description and content confirm the document is a subsidiary list; they cannot override a contradictory authoritative type without quarantine. Format-specific adapters support HTML, plain text and PDF. Image-only or encrypted documents require an explicitly approved deterministic OCR path; otherwise they are quarantined.

For each row preserve:

- legal name, jurisdiction and DBA names;
- explicit ownership percentage or immediate-parent text when present;
- table/row ordinal or byte/DOM locator;
- footnotes, omission language and source as-of date;
- original bytes, SHA-256, document identity and parser version.

Normalization uses Unicode NFKC, whitespace/entity cleanup and detached footnote markers. Raw display text is retained. Legal-suffix normalization is used only for comparison. Jurisdiction maps to a versioned country/subdivision vocabulary. Equal normalized name plus jurisdiction deduplicates within one exhibit; equal names in different jurisdictions remain distinct.

Visual indentation alone never establishes parentage. Prospective language is unresolved until a dated effective event is proven.

## Candidate outcomes

- `applicable_loaded`: one subsidiary row resolves to one source entity, the registrant resolves by filing CIK, and one relationship version is bound;
- `not_applicable`: only `explicit_no_subsidiaries`, `explicit_no_disclosable_subsidiaries_601_b21_ii`, or an evidenced form-rule boundary;
- `superseded`: a later effective exhibit replaces the source and identifies its successor;
- `unresolved`: missing exhibit/reference, unsupported foreign form, missing as-of date, prospective relation, or ambiguous entity;
- `quarantined`: corrupt bytes, parser row-boundary failure, contradictory duplicate, self-parent, unsupported image artifact or checksum mutation;
- `retryable_failed`: bounded SEC/S3 transport failure only.

Absence of an exhibit is never by itself `not_applicable`. Empty parse output passes only when the source explicitly says there are no subsidiaries or no disclosable subsidiaries. GO requires zero missing, unresolved, quarantined and exhausted retryable candidates.

## Entity resolution and temporal model

The parent target is the exact filing registrant CIK. Resolve the subsidiary in order:

1. explicit subsidiary CIK or authoritative SEC source reference;
2. existing exact exhibit-source identity;
3. unique normalized legal name plus jurisdiction with corroborating evidence;
4. otherwise create a deterministic non-CIK legal-company identity keyed by the filing registrant, normalized legal name and jurisdiction.

Fuzzy matches never auto-accept. The current company model assumes a unique CIK; implementation must support legal-company entities without CIK rather than manufacturing identifiers.

`effective_from` is the exhibit's explicit as-of date or, secondarily, the annual report date with provenance `inferred_annual_period`. Missing both is unresolved. The next effective disclosure closes the previous **reported** version. Disappearance from a later roster means “no longer disclosed under this source,” not proven dissolution or divestiture.

MDM relationship versions are authoritative. [`mdm_company.parent_company_entity_id`](../../edgar_warehouse/mdm/database.py) may be a convenience projection only when one current parent exists; the current derivation in [`pipeline.py`](../../edgar_warehouse/mdm/pipeline.py) must be replaced by evidence-driven versions.

## Acquisition, retry and repair

Use the existing SEC identity, host allowlist and rate limiter. Immutable cache hits make no SEC request. HTTP 429 honors `Retry-After`; timeout/5xx use bounded exponential backoff and jitter. An index-declared document returning 403/404 becomes unresolved after bounded attempts. Parser, schema and identity failures do not retry until a relevant version changes.

`--force` requires an accession/document repair manifest and retains prior artifact hashes and ledger outcomes. Post-acceptance SEC corrections create a new inventory fingerprint; activated evidence is never overwritten.

## Completeness and graph proof

Every applicable row binds to exactly one generation-eligible `HAS_PARENT_COMPANY` version with source system `sec_exhibit_subsidiaries`. Every not-applicable candidate has evidence and no edge. A `valid_zero` classification is permitted only after the complete registrant-period inventory contains explicit terminal not-applicable outcomes and no unresolved source.

Exact MDM/Neo4j parity compares relationship-version ID, canonical endpoints, temporal bounds, source accession/document hash, `parent_scope`, and evidence fingerprint. It also proves zero missing/extra/dangling edges and zero inactive, quarantined or superseded leakage.

## Ownership and acceptance

- Warehouse Ingestion Builder: complete SEC history, attachments, references and immutable bytes.
- SEC Parser Builder: format adapters, row evidence, omission and prospective classification.
- MDM Builder: non-CIK company identities, resolution and temporal versions.
- Graph Operator: generation publication and exact parity.
- Release Owner: accepts the reported-registrant semantic, Form 20-F inclusion, 40-F boundary and zero-unresolved evidence.

Named people are assigned in the Release Evidence Manifest and cannot be inferred from commit authorship.
