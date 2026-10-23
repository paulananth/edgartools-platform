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

**Status:** open. Not blocked by #1121 (RDM is its own store).

- [ ] The operator's permission for the one OECD request
- [ ] RDM's typed value per code: spec, migration, draft/approve/publish, tests
- [ ] The code set drafted from the table, its diff shown, approved in the operator's words, published and pinned
- [ ] The answer key's loss-year ROIC values recomputed with the rate (ticket 44)
- [ ] Learning → skill
