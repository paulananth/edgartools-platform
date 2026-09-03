# 56 — Build the reference_catalog capture-parity harness

Type: task

Status: open

## Question

`reference_catalog` (Ticket 23) has never been compared against
`seed-universe`'s legacy `_sync_reference_data` fetch — no Decision-2
side-by-side proof exists (the same gate every other family needed before
[Ticket 27](27-contract-legacy-acquisition-bypasses.md) could cut it over,
per [Ticket 10](10-decide-migration-cutover-rollback.md)). Build the
comparison, mirroring [Ticket 51](51-build-filing-artifact-capture-parity-harness.md)
(`filing_artifact`'s harness) and [Ticket 53](53-drive-legacy-and-gated-capture-into-parity-diff.md)
(actually driving both paths and diffing): run legacy `seed-universe`'s
fetch and `reference_catalog`'s gated `drive-reference-catalog-discovery`
against the same live SEC snapshot, and confirm the resulting
`sec_company_ticker` rows are an equal-or-superset match on both sides.

Scope is narrower than Ticket 51/53's: `reference_catalog` covers a fixed
2-item candidate set (`company_tickers`, `company_tickers_exchange`), not a
CIK-bounded universe, so there's no "1-CIK then 100-CIK" staged scope here
— this is closer to a single full-catalog comparison.

This ticket only proves fetch-layer parity for `sec_company_ticker`. It
does **not** decide whether to cut `seed-universe` over to
`reference_catalog`'s output (that still needs
[Ticket 55](55-decide-whether-reference-catalog-retires-seed-universe.md)'s
other findings — Ticket 54's sync-state consolidation question — resolved
first, since `seed-universe` does four other things besides this fetch).

## Blocked by

Nothing structurally — `reference_catalog` (Ticket 23) is already merged
and live. Sequencing with Ticket 54's resolution is a planning preference,
not a hard block: this harness can be built and run independently.
