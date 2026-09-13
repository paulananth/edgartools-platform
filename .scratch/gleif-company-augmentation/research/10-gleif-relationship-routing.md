# GLEIF relationship-type routing decision

Date: 2026-09-12
Scope: research and specification guidance only; no schema or production
changes.

## Decision

Retain every published GLEIF relationship record in the shared evidence
capture with its exact directional type. Publish an MDM relationship only when
both endpoints have accepted local identities in domains that support that
type. Do not create a generic entity or a Company merely to satisfy a GLEIF
endpoint.

| GLEIF type | Direction and meaning | MDM route | First Company slice |
| --- | --- | --- | --- |
| `IS_DIRECTLY_CONSOLIDATED_BY` | child legal entity -> direct accounting-consolidating parent | New Company -> Company typed relationship; never reuse `HAS_PARENT_COMPANY` | Yes, when both endpoints are accepted Companies |
| `IS_ULTIMATELY_CONSOLIDATED_BY` | child legal entity -> ultimate accounting-consolidating parent | Separate new Company -> Company typed relationship | Yes, when both endpoints are accepted Companies |
| `IS_INTERNATIONAL_BRANCH_OF` | international branch -> head office | Future Branch -> Company/other legal-entity relationship | Capture only until a Branch domain exists |
| `IS_FUND-MANAGED_BY` | managed fund -> legally responsible management entity | New Fund -> Adviser or Company typed relationship; do not reverse into SEC `MANAGES_FUND` | Later Fund consumer |
| `IS_SUBFUND_OF` | sub-fund -> umbrella fund | New Fund -> Fund typed relationship | Later Fund consumer |
| `IS_FEEDER_TO` | feeder fund -> master fund | New Fund -> Fund typed relationship | Later Fund consumer |

The current `HAS_PARENT_COMPANY` means a subsidiary disclosed by an SEC annual
report points to that filing registrant. It does not assert an immediate or
ultimate accounting consolidating parent. The current `MANAGES_FUND` runs from
an SEC Form ADV adviser to a private fund and has its own temporal source
semantics. Neither is an exact semantic match for a GLEIF type.

## Evidence and temporal contract

GLEIF RR-CDF is directional. It preserves the start and end identifiers and
their node types, relationship type, relationship status and periods, and the
LOU-maintained registration and validation evidence. A node can be an LEI or a
GLEIS provisional node identifier, so an endpoint must not be assumed to be an
LEI or silently resolved as one.

For every captured record retain:

- relationship-record ID, start/end node IDs and node types, exact type;
- relationship, accounting, and document-filing periods;
- relationship status, registration status, managing LOU, validation source
  and corroboration;
- source publication/snapshot and record hash; and
- the run that observed, activated, superseded, or retired the evidence.

Golden Copy relationship records describe the current curated state and may
omit historical or erroneous records that remain in Concatenated Files. A
partial daily delta's absence therefore cannot retire a relationship. Retire a
published MDM version only from an explicit changed/deleted source outcome or
from a complete monthly reconciliation against a verified full snapshot. Keep
the superseded source version for audit.

If one endpoint is unknown locally, retain the source record with routing state
`blocked_missing_endpoint`; retry it in the weekly candidate backstop and
monthly reconciliation. If the endpoint category belongs to a not-yet-built
domain, use `deferred_unsupported_domain`. Neither state publishes a graph
edge.

## Reporting exceptions

Direct- and ultimate-parent reporting exceptions are evidence about why a
relationship is not published; they are not relationships and are not proof
that no real parent exists. Preserve them per child LEI and relationship
category with their reason and registration evidence. A current relationship
of the same type supersedes the corresponding current exception, but historical
versions remain auditable.

## Sources

- [GLEIF RR-CDF 2.1 format](https://www.gleif.org/en/lei-data/access-and-use-lei-data/level-2-data-relationship-record-rr-cdf-2-1-format)
- [GLEIF RR-CDF 2.1 documentation](https://www.gleif.org/content/4_lei-data/1_access-and-use-lei-data/4_level-2-data-relationship-record-rr-cdf-2-1-format/rr-cdf_version_2.1-documentation.html)
- [GLEIF Golden Copy and Delta Files manual](https://www.gleif.org/lei-data/gleif-golden-copy/2022-02-23_gleif-golden-copy-and-delta-files_v2.2-final.pdf)
- Repository `docs/release-readiness/parent-company-source-parser-contract.md`
- Repository `edgar_warehouse/mdm/migrations/runtime.py`
