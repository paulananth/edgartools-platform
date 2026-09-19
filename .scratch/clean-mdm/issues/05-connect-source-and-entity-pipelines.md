# Connect source and entity pipelines

Type: task
Status: open
Owner: Codex
Blocked by: 04

## Work

Route supported source adapters and existing mastering, relationship, stewardship and repair paths through shared transaction ownership; preserve entry points and dependency order. Approved extensions require concrete schemas and representative fixtures.

## Company-first delivery gate

User direction on 2026-09-19: SEC + GLEIF Company mastering has priority over
Person, ADV roles, Fund, Security and other entity integrations. Implement and
verify the [Company completion gate](../../../docs/specs/clean-mdm/company-completion.md)
first, including accepted OpenCorporates corroboration, Company consolidation
relationships, source changes and end-to-end local recovery. Do not close this
ticket from a SEC-only Company loader or advance other entity integration
before that gate passes. Broader ticket scope remains pending afterward.

## Evidence

First bounded native SEC Company preparation/normalization is implemented and
tested. A three-company candidate is pinned locally, but coverage activation,
identity review and persistent Clean MDM ingestion have not occurred. Other
source/role/relationship pipelines remain pending. Ticket 04 is still open.
See [build state](../../../docs/specs/clean-mdm/state-of-build.md).
