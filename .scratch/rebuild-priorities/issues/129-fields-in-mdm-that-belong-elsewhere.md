# 129: Fields in MDM that belong elsewhere (review of 2026-10-22)

Priority: 129. Map: [Rebuild priorities](../map.md). Raised by the operator's
review request, 2026-10-22: "Review using onboarding skill are there fields that
must be silver incorrectly in mdm"; rulings: "Fix 1, 2 date that changes usually
should not be in MDM unless it adds meaning to the entity or turn on or off".

Type: task. Status: in progress; #1121 merged 2026-10-22 19:08 ET, fixes 2 and 3 (the Company) built on it.

## What the review found

Every MDM field the 14 Dataset Contracts fill, checked against the
data-onboarding skill's map rules:

1. `issuer_lei` on the N-PORT Security: an LEI identifies a Company ("A value
   of another kind stays out of this kind"); the Security reaches its issuer by
   ISSUED_BY (ticket 22). The filed LEI is evidence of the holding.
2. `gleif_last_update` and `gleif_next_renewal` on the Company: GLEIF's
   record-keeping dates; they change at each renewal and give the Company a new
   version without a change in the entity. GLEIF's record already carries
   LastUpdateDate as its effective time.
3. `sic_description` on the Company: a code's label, which belongs in an RDM
   SIC code set (the Company keeps `sic`).
4. `share_class_figi` on the OpenFIGI Security: a field and a cross-reference
   both; the cross-reference alone is enough.
5. Not a field: the Form ADV custodian Dataset Contract keys its records on
   `[published, custodian_id]`, so each publication makes a new MDM record for
   the same custodian; the publication date belongs in the publication key.

Clean: no amounts, positions, transactions or quarter dates are in MDM.

## Checklist

- [x] Review of every Dataset Contract's MDM fields (2026-10-22 11:27 ET)
- [x] Fix 1: `issuer_lei` out of the Security's Dataset Contract; the filed LEI is a column of the silver holding row (`silver-holding.yaml`); MAPPING.xlsx and security.xlsx regenerated; tests: N-PORT, OpenFIGI and rules 77 passed, MDM folder 896 passed (2026-10-22 11:27 ET)
- [x] Fix 2: `gleif_last_update` and `gleif_next_renewal` out of the Company: a migration that drops the two Company columns and the field writer's use of them; the census contracts' copies; the cascade and census matching check freshness against the GLEIF record's effective time (`cascade.py:138`, `matching.py:117,142`), not the field. `matching.py` is in Codex's open PR #1121, which also adds MDM migration 024; built right after #1121 merges, on its numbering (operator, 2026-10-22: "Wait for #1121 (Recommended)"). Built: GLEIF's two dates are no longer fields of the GLEIF Level 1 contract (`source.yaml`, `level1-fields.yaml`). The two census matching rules (`record_pairs.rs`, `name_census_match@1` and the cascade pass) read the stored record's effective time, which is GLEIF's LastUpdateDate in UTC, and compare it with the census's raw LastUpdateDate as an instant (`same_update`); a string comparison would have refused every record whose spelling differs. The census contracts and `cascade.py` keep their own copy of LastUpdateDate: it lives only in the census's private projection, never in the Company. Migration 026 recreates the Company writer without the columns and drops them. Overlap: a Codex worktree (`mysql-mastering-merging-20261019`) holds 2-day-old drafts of `record_pairs.rs` and `matching.py`; operator: "Go ahead (Recommended)" (2026-10-22 19:18 ET). Tests: matching 14 (GLEIF's spelling and the UTC form one instant; a later version refused; unknown only with unknown; the cascade pass the same), digest layers (each contract with the fields put back is the one pinned before: 119), the cohort (with the field back, both old hashes), integration 18 on PostgreSQL 16 (026 on a populated store keeps every version's body and chosen fields; 015's migration test; name matching), engine 33 groups; MAPPING.xlsx for gleif and sec.submissions.company and company.xlsx regenerated, `mapdoc check` passes (2026-10-22 19:45 ET)
- [x] Fix 3, the code set (operator, 2026-10-22: "Fix 3"): RDM `sec-sic-codes` version 1, 407 codes from the captured submissions (76,230 companies, 9,533 with a SIC code; every code one description; `0000` on 38 companies with none, kept invalid: "no SIC code assigned"); approved "Approve version 1 (Recommended)", published through the real path on a disposable PostgreSQL 16, sha256 `b8ca5d43…`; `rules/reference/published/sec-sic-codes/1/`; RDM tests 57 passed (2026-10-22 11:36 ET)
- [x] Fix 3, the Company: `sic_description` out of the Company's Dataset Contract and its column dropped; with fix 2's migration after #1121 (operator, 2026-10-22: "Wait for #1121 (Recommended)"). Silver keeps the filed description. Built: `sic_description` leaves the Company's Dataset Contract (its fields and `input_fields`) and migration 026 drops the column; the source extract and preparation keep it for silver. Its other readers were checked: the Snowflake mirror (`09`), the export target (`07`), gold `mdm_company.sql`/`company.sql`, the dashboard registry and Streamlit read the old pipeline's export tables or silver, never MDM's PostgreSQL column, so nothing live moves (2026-10-22 19:45 ET)
- [x] Fix 4 (operator, 2026-10-22: "Fix 4"): `share_class_figi` is no longer a field of either OpenFIGI Security contract; it stays the Security's lookup cross-reference, so ticket 120's "all fields from open figi must be in the security master" still holds. MAPPING.xlsx and security.xlsx regenerated; no merge-policy fingerprint moved (MDM 896 passed; OpenFIGI, holding and mapdoc 36 passed) (2026-10-22 11:43 ET)
- [x] Fix 5 (operator, 2026-10-22: "Fix 5"): `iapd.adv.custodians.v1` keys on `custodian_id` alone, and the CUSTODIAN link targets `[item]`; each monthly file is its own publication with its month (YYYYMM) as `revision` and its month end as `effective_at`, written in the contract for the run that prepares it. Test: May and June make one record per custodian, June a later revision, one link per custodian; custodian, catalog, mapdoc, N-PORT and OpenFIGI 58 passed, MDM 896 passed (2026-10-22 11:49 ET)
- [x] Fixes 1, 3 (code set), 4 and 5 merged: PR #1133, CI green (2026-10-22 12:03 ET)
- [x] Fixes 2 and 3 (the Company): three-axis review. Spec: no findings (no reader of the three columns left; `same_update` right in each case; 026 keeps the writer's grants and drops without a table rewrite). Standards: two fixed (the test helpers named for the fields they put back, `_with_company_fields_back`; the matching rule's condition chain indented as one expression); engine tests and digest, cohort and matching 135 passed. GoF: one finding, deferred below (2026-10-22 19:49 ET)
- [ ] ~~GoF: the digest test's undo chain as one ordered list walked by a loop~~ deferred to its own ticket: it changes every pinned layer, not ticket 129's fields; each ticket that moves a contract adds one more hand-written layer today
- [x] First CI run on PR #1141 failed, 28 engine tests and 1 unit test; fixed (2026-10-22 20:03 ET):
  - the SEC Company `fields.yaml` recipe still listed `sic_description`, which broke the inline-equals-recipe checks and the installed bundle test; removed;
  - the GLEIF and SEC tests that compare with the retired mapper's answers now compare with the ticket 129 fields put back (`tests/support/company_fields.py`, shared with the digest layers, as Person's `before_ticket_10`);
  - the skill line named a source outside the Examples; it now names the ticket only;
  - engine 1,021 passed locally without the PostgreSQL bundle file; digest, cohort and the two fields files 215; genericity 78
- [ ] Fixes 2 and 3 (the Company): CI green, merge (PR #1141)
- [ ] Deploy: migration 026 runs on the hosted MDM only with the operator's word (`mdm migrate` is explicit). Expected: stored Company bodies still hold the three old fields, so the first merge after 026 writes one new version of each Company with GLEIF or SEC evidence that held them
- [x] Learning → skill (fixes 2 and 3): `skills/refining-rules/SKILL.md`, change-matching: a rule comparing two records' times compares instants, never text; a record-keeping date that only marks a new version is the record's effective time, not a master field. (`skills/mdm-engineering/SKILL.md` was the first choice; a Codex worktree is changing it, so the line went beside the matching rules instead.) (2026-10-22 19:46 ET)
- [x] Learning → skill: `skills/data-onboarding/SKILL.md`, Record key: no publication time in a record key; a restating feed gives each delivery its own publication and a rising revision; a one-part key is the plain value. `skills/data-profiling/SKILL.md`, Reference data: evidence is an object; publish writes `<folder>/<code set>/<version>/`, the repo keeps canonical and pin, sha256 checked; a disposable PG16 needs a database named `rdm`. `skills/data-onboarding/SKILL.md`, map "Fields": a date that usually changes stays out of MDM unless it adds meaning or switches the entity on or off; evidence about a link stays on the silver row. `skills/refining-rules/SKILL.md`: which target a field belongs to (name every engine reader before moving one), and a field change regenerates both the source and the kind workbook (2026-10-22 11:27 ET)
