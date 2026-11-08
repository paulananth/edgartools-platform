# Mastered entity and downstream data audit

**Status: IN PROGRESS.** Audit every populated MDM kind through its configured
source fields, relationships, and downstream fields, then turn only
evidence-backed defects into repeatable data-quality checks. Scope includes
Companies, international entities, N-PORT fund structures, private-equity
representation, people, securities, and any other populated entity kind. This
covers MDM and Silver; Gold is out of scope.

## Work

- [01 — Trace mastered entity fields and relationships, then define data-quality checks](issues/01-company-field-and-relationship-quality-checks.md)

Use the existing AAPL trace as the control case. Follow the same configured
source, master, relationship, and downstream paths for the full Company
population. Check definitions must follow this repository's data-quality
engine and may use DataKitchen TestGen as a reference for check categories;
TestGen is not a runtime dependency.

The configured MDM catalog has eight kinds. The observed populated legacy MDM
snapshot has four: Company (10,698), fund structure (12,937), person (31,125),
and security (393,683). Branch, government, international organization, and
venue are configured but had no legacy master rows in that observation. A
fund profile is also permitted on Company, so fund coverage must include both
Company fund profiles and fund-structure masters. `private_equity` is not a
configured MDM kind; classify its actual representation from the configured
Company/fund rules and evidence rather than inferring it from a private-offering
form. Non-US companies remain in the Company kind, whose configured jurisdiction
field is sourced from GLEIF; report that subgroup separately from the configured
`international_organization` kind.

The Silver identity contract needs a cutover trace. Of 55,320 Silver
relationship rows, all resolve to legacy master IDs and none resolve to current
governed MDM IDs or scanned current MDM history. Legacy masters contain 42,383
`ISSUED_BY` edges, while governed MDM contains 505. The checked-out code at
`8fb535d` reads Silver link IDs from governed MDM and no longer implements the
relationship-table builder, but the local PostgreSQL server only stores data;
it does not establish which worker code produced those rows. Two
`sec.nport.security` Bookkeeping runs also remain `running`, with their
`land_holding` work pending. Treat these as observed identity and run-state
mismatches with unresolved producer/version ownership; do not refresh, delete,
or recreate links until the deployed worker and cutover contract are verified.
