# Implement the Current-Model Hosted ADV Private-Fund Load

Type: task
Status: open
Blocked by: none
Blocks: none
Labels: wayfinder:task

## Task

Build and qualify an isolated hosted load of the retained Form ADV Schedule D 7.B(1)/(2) monthly data through the current Bookkeeping source path. Use the current MDM model: Adviser is a governed profile on a Company or Person, private funds are Fund Structures keyed by PFID, and the relationship is `INVESTMENT_ADVISER_TO`. The destination is hosted Snowflake Silver/MDM and the existing hosted graph publication path.

### Current evidence

- `rules/sources/iapd.adv/source.yaml` currently reads adviser filings, custodians, CIKs and related persons; it has no 7.B(1)/(2) private-fund reading or Fund Structure target.
- `CONTEXT.md` defines Adviser as a profile, Fund Structure as the private-fund identity, and `INVESTMENT_ADVISER_TO` as the adviser-to-fund relationship. `rules/merge/kinds/fund_structure.yaml` currently binds N-PORT and N-CEN sources, not IAPD.
- `docs/release-readiness/adviser-fund-source-contract.md` still describes the older separate Adviser identity and `MANAGES_FUND` graph contract. Reconcile that legacy contract to the current domain model rather than copying its obsolete entity names into the new source.
- `docs/specs/source-readiness.md` reports `iapd.adv` as unwired; the current source file now declares Bookkeeping targets, so qualify actual runtime support rather than treating either static statement as proof.
- The retained 13-month archive evidence is not itself a current Bookkeeping capture: the proof directory has no `receipts.jsonl` or producer `capture-run` identity. A complete supported capture is a load prerequisite.

### Required work

1. Extend the current `iapd.adv` source and Dataset Contracts to read Schedule D 7.B(1) and 7.B(2) from the monthly archive, join rows to the correct filing, and preserve PFID, CRD, section, reporting role, filing action, effective time, and source provenance. Keep master and feeder fund identities distinct; resolve fund identity by PFID, never by name.
2. Map advisers to their current Company/Person masters and funds to Fund Structures, then emit `INVESTMENT_ADVISER_TO` with the source evidence and effective interval required by `CONTEXT.md`. Retain multiple advisers reporting the same PFID as separate relationships; do not mint a second fund identity for an amendment or another adviser.
3. Keep one month as one publication with its own `published` fact. Process the approved rolling 13-month window in the correct order, with idempotent replay and no deletion based on absence. Preserve the approved source and merge-rule lifecycle; do not activate a changed Rules version without its required proof and operator approval.
4. Use the current `edgar-warehouse load`/Bookkeeping worker-verifier path against the complete captured delivery and configured hosted connections. Load Silver to Snowflake `EDGARTOOLS_SILVER` and MDM to Snowflake-hosted Postgres. Do not use the retired `edgartools-prod-load-history` Step Function or invoke a broad full-history/Gold pipeline for this isolated load. If complete capture receipts or hosted connections are unavailable, stop and record the blocker; do not fabricate receipts or make a provider request.
5. Verify the full input inventory, per-month work accounting, MDM Fund Structure/relationship results, Snowflake Silver readback, and exact hosted graph parity for the current relationship type. Confirm an unchanged replay is a no-op. Record run/capture references and counts only; keep row-level records and credentials private.

## Acceptance

- Both 7.B sections are represented without loss of filing/PFID lineage, including 7.B(2) cross-references and amendments.
- Each PFID resolves to one Fund Structure; Adviser profiles resolve to their existing Company or Person identities; every accepted relationship is `INVESTMENT_ADVISER_TO` and retains its source evidence/effective interval.
- The entire approved captured window is accounted for as loaded, already processed, deferred, or rejected; no records disappear silently.
- The supported hosted run completes with independent verification and Change Journal delivery. Silver, MDM and graph readbacks reconcile; the same capture/rules replay creates no duplicate identities or relationships.
- No legacy workflow or unapproved provider request is used.

## Checklist

- [ ] Reconcile the legacy Adviser–Fund contract and source rules to the current Company/Person, Fund Structure and `INVESTMENT_ADVISER_TO` model; record the approved rule changes and proof.
- [ ] Add 7.B(1)/(2) readings, joins, Dataset Contracts and Fund Structure relationship processing with regression tests for encoding, PFID identity, 7.B(2), amendments, duplicate/conflicting rows and replay.
- [ ] Establish a complete supported capture manifest/receipts and its producer run identity for the intended monthly window; if unavailable, leave this part open and name the acquisition authorization needed.
- [ ] Run the isolated Bookkeeping load against hosted connections; verify Silver, MDM, Journal and graph outcomes and record counts/run IDs privately.
- [ ] Update the current source/runbook documentation to match the shipped path.
- [ ] Learning → skill: record the verified hosted ADV source/load procedure in the owning skill.
