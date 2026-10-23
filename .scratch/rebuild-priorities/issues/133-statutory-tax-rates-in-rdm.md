# 133: Statutory corporate tax rates in RDM

Priority: 133, tier 3, product value. Map: [Rebuild priorities](../map.md). Opened 2026-10-22
from [44: the answer key](44-company-financials-12-answer-key-for-measures.md).

**Why:** ROIC is EBIT × (1 − tax rate) over invested capital (ticket 39). When pretax
income is zero or negative, or the effective rate falls outside 0–100%, the rate is the
statutory rate of the filer's country (operator, 2026-10-22: "Statutory rate (new
source)"; Damodaran's practice). The rates are reference data: an outside authority's
short list, keyed by a standard code, looked up by many records (operator: "Should this
be in rdm", then "RDM, OECD source (Recommended)").

**What to build:**
- RDM gains a typed value per code: `value` (exact decimal) and `unit`, beside the
  code's label and its `valid_from` / `valid_to` (`docs/specs/rdm/spec.md`).
- Code set `corporate-tax-rates`: one code per country (ISO 3166 alpha-2), each rate a
  period on its code; a new year's rates are a version that supersedes the last.
- Source: the OECD Corporate Tax Statistics statutory corporate income tax rate table
  (combined central and sub-central rate), fetched once with the operator's permission
  for that request, drafted, approved and published like any code set.
- ROIC takes the rate of the filer's country of incorporation in force at the fiscal
  year's end.

**Status:** in progress (Claude, branch `claude/t133-tax-rates`).

- [x] The operator's permission for the one OECD request: "work on this and complete", written on this ticket's box of the route plan (2026-10-23 10:24 ET). The one request (2026-10-23 10:29 ET): `https://sdmx.oecd.org/public/rest/data/OECD.CTP.TPS,DSD_TAX_CIT@DF_CIT,2.0/all?dimensionAtObservation=AllDimensions&format=csvfilewithlabels`, HTTP 200, 5,037,981 bytes, 13,752 rows, sha256 `6855684f67ceb0c3a46478d80383c7e963ca09629a9c5a5a625312339e1fcd68`; kept locally with its receipt, never fetched again. The address was found through a search engine and a third-party mirror, so no other request reached the OECD
- [x] RDM's typed value per code (2026-10-23 10:47 ET): `rdm.code` gains `value` (exact decimal text, checked) and `unit`, both or neither; a rate per year is a child code of its country dated to its year (the model's own `valid_from`/`valid_to` and one parent), so no new table, trigger or grant. PostgreSQL migration `004_code_value.sql`; MySQL `mysql-value-v3.sql`, checksummed and resumable like the search migration. The canonical form carries `value` and `unit` only on a code that has one, so every published pin is unchanged (a test rebuilds all 5 published versions in the repository to their pinned bytes). GoF: leave it (the per-code lists were written once, in #845). Tests: reference unit 41; RDM integration on PG16 13 (a value round-trips and is pinned, a published value cannot change, a bad value is refused, 004 on a store published before it keeps its pin); storage on PG16 66; storage and MySQL recovery on MySQL 8 79 (drift refused, an interrupted value migration resumes); Rust reference 3. Spec §2.1, §4 and Examples
- [ ] The code set drafted from the table, its diff shown, approved in the operator's words, published and pinned
- [ ] The answer key's loss-year ROIC values recomputed with the rate (ticket 44)
- [ ] Learning → skill
