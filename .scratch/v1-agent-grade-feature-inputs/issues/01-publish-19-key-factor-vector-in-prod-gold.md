# 01 — Publish the 19-key factor vector in prod gold

**What to build:** Prod gold As-Of Decision Features expose the locked 19
keys, including EBITDA, diluted EPS, and EBITDA margin, for every CIK that
already has derived rows. A Feature Screen bind can read those keys. This
does not add companies.

**Blocked by:** None — can start immediately.

**Status:** ready-for-agent

- [ ] Live gold factor columns include all 19 locked keys (EBITDA, diluted EPS, and EBITDA margin among them).
- [ ] Those three passthrough keys are populated from existing derived values, not left all-null.
- [ ] Distinct CIK count on gold factors is unchanged from the current 21-CIK sample (this ticket does not backfill the universe).
- [ ] Operating margin is not used as a stand-in for EBITDA margin.
