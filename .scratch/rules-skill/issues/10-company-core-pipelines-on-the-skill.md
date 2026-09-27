# Company core pipelines on the skill

Type: task
Status: open
Blocked by: 04 (a preview), for the approval step only

## Outcome

Operator, 2026-09-26: "incorporate all company data pipelines and test".
Company core runs through the rules files, the Rules Database and the
Bookkeeping skill, with no second path:
- SEC submissions (`sec.submissions.company`);
- the SEC ticker lists (`company_tickers`, `company_tickers_exchange`),
  which feed only the Company rule today; tickers belong to Security;
- GLEIF Level 1, relationships and reporting exceptions (`gleif`).

## Known work, from the trials (ticket 07)

- A new SEC source code, `sec.submissions.company.v2`: EIN and SEC's LEI
  become lookup-only identifiers (operator, 2026-09-26), and identifiers are
  fixed within one source code (`PROTECTED_ADAPTER_PARTS`). The same change
  takes capture hashes, run id and sync time out of `provenance` (operator,
  2026-09-27). The reader must first land SEC's LEI.
- "Trace beside the record" is not fully true until the reader changes too:
  its publication key is built from the run id and file hashes, and the
  Name Census entry kept for matching carries the census digest, so every
  capture still gives each fact a new fingerprint. The publication key is
  also fixed within one source code.
- GLEIF relationships: the Company merge rules must list
  `gleif.relationships.v1`, and an LEI matching rule must exist, before a
  relationship becomes a link. Both need the operator's approval.
- **Decided (operator, 2026-09-27 13:40 ET, "agreed"):** a GLEIF
  relationship of a type not mapped yet (the three fund types and the
  branch type) waits without stopping the run. So each GLEIF contract lists
  `unsupported_relationship_type` as non-blocking, in a new GLEIF version
  that the operator approves. Each run reports the waiting records counted
  by type, so a type GLEIF adds later is seen, because the reader does not
  check type names.
- Open operator questions: whether SEC filers held back by the Company rule
  block; whether GLEIF's other entity ids are lookup-only identifiers;
  whether relationship records carry the start LEI as `lei`.
- Reader defects from company-mastering ticket 18 (check digit before scope,
  `NULL` statuses, the `P7` region, ICONIQ).

## Test

Each source: save, prove, approve (the operator), activate, then a bounded
run through `$bookkeeping validate` on isolated PG16 stores, with record
counts that match the trials' dry runs.
