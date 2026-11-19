# Gold design, first slice: 13F holdings

Status: open
Type: task

Applies [the Gold warehouse method](../../../skills/data-modeling/GOLD.md) (ticket 01) to one slice, to find where the
method is thin. It is a design record: no dbt, no destination, no mirror. Inputs are the approved exposure list
(`rules/exposure.yaml`, `exposure-2026-11-18.silver-mdm-and-published-rdm-codes`).

## Parts

- [x] Read the method, the two silver specs and the exposure entries for the slice. 2026-11-19 08:29 ET
- [ ] Operator reviews the design below (grain, dimensions, the six open questions)
- [x] Refine `GOLD.md` with the four gaps the slice found, as proposed rules the operator may strike: genericity, no-ticket and guide-path tests, 148 passed. 2026-11-19 08:29 ET
- [ ] Count, on the loaded stores, the rows each join would multiply or drop (needs the load)
- [ ] ~~dbt generator and models~~ deferred: the writable destination is not approved (GOLD.md, "dbt implementation requirements")
- [ ] Learning → skill: `GOLD.md`, the gaps below once confirmed

## Design (method's "What to write down")

**Technique.** Conformed dimensional bus. Direct mirror reads do not satisfy the requirement "holdings by manager, by
security, by quarter with names and attributes": the facts hold keys, the attributes sit in a JSON `body` on the
master, so a transformation is needed.

**Facts**

| Fact | Grain sentence | Type | Measures | Time |
|---|---|---|---|---|
| `fact_13f_holding` | One row per filing (accession number) and holding (its place in the information table) | Transaction fact of a reported position | `shares_held`, `market_value`, `voting_auth_sole/shared/none` (each its own unit: see Gaps 2) | business: `report_date`; recorded: `filing_date` (both from `thirteenf_filing`) |
| `fact_13f_filing` | One row per accession number and manager | Factless fact (a filing exists) | none | same two columns |

**Dimensions (conformed, one per kind, current master)**

| Dimension | Key | Roles on this slice | Source |
|---|---|---|---|
| `dim_company` | MDM id (`manager_mdm_id`) | manager | `mdm.mastering_master`, kind company, canonical records only |
| `dim_security` | MDM id (`security_mdm_id`) | held security | `mdm.mastering_master`, kind security, canonical records only |
| `dim_date` | calendar date | business time (`report_date`), recorded time (`filing_date`) | generated |
| code sets | published version | `share_type`, `put_call`, `discretion_type` if they are code sets; otherwise degenerate attributes | `rdm.published_code` |

**Inputs.** `silver.thirteenf_holding`, `silver.thirteenf_filing`, `mdm.mastering_master`, `rdm.published_code`: all on the
approved list. Whether `mastering_master` serves a per-kind dimension (one `body` JSON for every kind, alias rows beside
canonical ones) is proposed, not proven.

**Time scope.** Facts: history (both silver tables are append). Dimensions: current.

**Direct mirror reads suffice?** No (above). **Destination:** pending the operator's approval of an exact writable
database and schema.

## Gaps in the method (the slice found these)

1. **A holding names a key no master has.** `thirteenf_holding.cusip` fills `security_mdm_id` by lookup; an unmastered row
   keeps its source key and an empty id (data-onboarding). `GOLD.md` says every fact joins a dimension but not what an
   empty or unknown key becomes. Proposal: an explicit "unknown" member per dimension, the fact's key never null, and a
   count of rows on it reported with the build.
2. **One measure, several units.** `shares_held` counts shares for `SH` and a principal amount for `PRN`, and `put_call`
   rows are options on the security, not the security. Summing `shares_held` across them is wrong. The method keeps "the
   unit beside the amount" but does not say a measure with a unit column is additive only within one unit.
3. **A holding's date lives on another silver table.** The holding has no report date; `thirteenf_filing` does, one row per
   accession *and manager*. A filing listed by two managers has two rows, so joining holding to filing on accession alone
   multiplies holdings. Section "One grain" point 6 names the risk; it gives no rule for which key makes a join safe.
   Proposal: a fact takes dates from a sibling silver table only through that table's whole key, or the sibling is first
   reduced to one row per the fact's key.
4. **Dimensions read JSON.** Masters are one `body` per kind. The method says "a view per kind" but not that the view
   unpacks typed columns from the master's declared fields, drops alias rows and carries the kind filter, so adding a
   field is a declaration, not view code (the kind files already declare the fields).

## Open questions for the operator

1. Amendments (13F-HR/A) are new accessions. Does the first requirement need "the position as last amended for a
   manager and quarter"? If yes, that is a derived snapshot fact and its definition needs an owner (GOLD.md point 4);
   recommended: not yet, keep the transaction fact.
2. Is `market_value` in whole dollars for every report period? The silver definition says US dollars; a change in the
   source's own unit over time is unverified and must be profiled before any sum across quarters.
3. Which attributes does a requirement need on `dim_company` and `dim_security`? Recommended: only those the requirement
   names (name, identifiers, status), so the dimension stays small.
4. The approved writable destination (database and schema) and the dbt role and warehouse.
5. Which of `share_type`, `put_call` and `discretion_type` are code sets in RDM, and which stay attributes.
6. Do the issuer attributes of a security (its issuing company) belong on `dim_security`, or is that the relationship
   bridge joined when asked?
