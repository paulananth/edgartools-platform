# Relationship Eligibility at the Release Watermark

## Decision

The initial production generation requires all eleven registered relationship types. A type being required does not mean that every entity must have an edge of that type. Optionality is represented per source candidate through a generation-bound applicability ledger, not by excluding the relationship type from release scope.

The eleven required types are:

- `IS_INSIDER`
- `HOLDS`
- `COMPANY_HOLDS`
- `ISSUED_BY`
- `IS_ENTITY_OF`
- `IS_PERSON_OF`
- `MANAGES_FUND`
- `HAS_PARENT_COMPANY`
- `EMPLOYED_BY`
- `AUDITED_BY`
- `INSTITUTIONAL_HOLDS`

No relationship type classified as `excluded` is acceptable in a GO generation.

## Frozen Generation Boundary

All eligibility, applicability, coverage, publication, and parity evidence for a generation must derive from one transaction-consistent Relationship Generation Snapshot tied to the committed Release Data Watermark.

The snapshot freezes:

- the complete source-candidate inventory;
- MDM relationship types and relationship versions;
- canonical endpoint resolution;
- applicability outcomes;
- coverage records;
- graph node and edge partitions;
- parity counts and digests.

Changes committed after the watermark belong to the next generation. A builder must not repeatedly query mutable live tables and approximate a snapshot with timestamp filters. Activation fails if the snapshot fingerprint or watermark drifts from the committed publication request.

## Generation Eligibility

A relationship version is generation eligible when all of the following hold in the frozen snapshot:

- its relationship type is active;
- the relationship record is active;
- the version is not quarantined;
- the version has not been superseded;
- both canonical endpoints resolve to nodes included in the same generation.

The generation preserves all eligible relationship-version history committed by the watermark, including ended versions. The current-at-watermark subset is derived separately using the half-open interval `[valid_from_date, valid_to_date)`. Versions with unknown temporal bounds remain visible in history but are excluded from strict as-of results unless the query explicitly requests temporal uncertainty.

The current graph-generation predicate that relies only on active relationship and type flags is insufficient. It must also enforce quarantine, supersession, canonical-endpoint, generation, and snapshot-boundary rules.

## Applicability Ledger

Every source candidate or candidate pair for every required type must have exactly one generation-bound outcome:

- `applicable`: the candidate produces one or more authoritative relationship versions;
- `not_applicable`: the relationship legitimately does not exist, with a stable reason code and supporting evidence;
- `unresolved`: the candidate cannot yet be conclusively classified.

The Relationship Applicability Ledger must be complete, fingerprinted, and tied to the generation snapshot. GO requires:

- zero missing source candidates;
- zero unresolved candidates;
- every applicable candidate bound to the resulting MDM relationship versions and graph parity evidence;
- every not-applicable outcome supported by a stable reason and source evidence.

The completeness denominator is the complete source-candidate inventory or applicable candidate pairs, not all entities in the universe.

## Coverage Records

Each active relationship type must have exactly one fresh Relationship Coverage Record for the generation:

- `populated`: the type has a nonzero eligible relationship count and passes exact parity;
- `valid_zero`: the complete supported source load and derivation ran successfully, the applicability ledger is complete, and the authoritative eligible count is genuinely zero;
- `excluded`: a documented source or capability boundary.

Coverage classification is recomputed for every generation and cannot be permanently hardcoded by type. Missing, stale, contradictory, or fingerprint-mismatched coverage blocks activation. For the initial GO generation, `excluded` is never acceptable because all eleven types are required.

A known ingestion, parser, entitlement, or derivation gap cannot be reported as `valid_zero`. No synthetic relationships may be introduced to satisfy a count.

## Exact Per-Type Parity

For every required type, the frozen MDM snapshot and hosted Neo4j generation must prove:

- equal generation-eligible counts;
- zero missing and zero extra relationship versions;
- equal relationship-version identity digests;
- equal canonical property and temporal digests;
- endpoints resolving to nodes in the same generation;
- zero inactive, quarantined, superseded, or discarded-endpoint leaks;
- equal current-at-watermark subset counts and digests;
- for a proven `valid_zero`, zero records on both sides plus a fresh matching evidence fingerprint.

Hosted verification must read through the same active-generation pointer that production queries use. Any mismatch blocks activation.

## Current GO Blockers

The existing capability gaps are release blockers, not allowable exclusions:

- `EMPLOYED_BY` and `INSTITUTIONAL_HOLDS` require completion of the applicable bulk-source load, derivation, publication, and parity proof, including the currently gated DEF 14A, 8-K, and 13F-HR inputs.
- `MANAGES_FUND` requires an approved adviser/fund source contract and ingestion path for IARD/IAPD or an equivalent authoritative source.
- `HAS_PARENT_COMPANY` requires the parent-company source and Exhibit 21 parsing capability.
- `AUDITED_BY` requires an authoritative auditor-evidence ingestion contract because the existing company-facts path does not supply the required evidence.
- Every other required type must also demonstrate complete candidate coverage and exact parity at the release watermark; prior populated or zero labels are not sufficient by themselves.

## Ownership and Gate

- The source/candidate builder owns complete candidate enumeration and applicability evidence.
- The MDM operator owns derivation, version eligibility, coverage records, and the frozen snapshot fingerprint.
- The graph operator owns generation publication and hosted parity evidence.
- The Release Owner accepts GO only when all eleven types pass and no exclusion, unresolved candidate, missing candidate, stale evidence, or parity mismatch remains.

This gate is a hard dependency of the Full-Chain Launch Gate.
