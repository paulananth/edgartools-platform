# 02 — `run_companies()` resolves Form D issuers, registered funds, and 13F-only investment managers as `mdm_company` entities

**Status:** open

**What was found (2026-09-07):** follow-on to Ticket 01. After the
individual-reporting-owner exclusion filter shipped (Ticket 01, merged
`12b23891`), the user asked why `sec_company` still yields 30K+ "companies"
when real operating companies are added and retired at a much slower,
roughly-bounded rate. Live data confirms the intuition is right — the
excess is not operating companies at all.

**Live breakdown of the 50,735 CIKs that survive Ticket 01's individual
filter** (`SnowflakeSilverReader`, prod, queried directly):

| Category | CIKs | What they are |
|---|---|---|
| Ever filed a real periodic disclosure (`10-K`/`10-K/A`/`10-Q`/`10-Q/A`/`8-K`/`8-K/A`) | 7,505 | Genuine operating companies — roughly the bounded population you'd expect |
| Zero `sec_company_filing` rows at all | 10,794 | Discovered (daily-index/submissions) but no filing ever parsed into silver — likely brand-new CIKs or an artifact-fetch gap, tracked separately, not this ticket's concern |
| Has *some* filing history, but never a periodic-disclosure form | **32,436** | This is the "30K+" the user is asking about |

**Form-type histogram of that 32,436-CIK bucket** (top entries, `cik_count`
= distinct CIKs filing that form):

- `D` / `D/A` (Reg D private placement notice): 15,109 / 6,037
- `N-PX` (fund proxy voting record): 10,010
- `13F-HR` / `13F-HR/A` / `13F-NT`: 9,294 / 3,983 / 2,210
- `SC 13G` / `SC 13G/A` / `SCHEDULE 13G/A`: 2,964 / 2,562 / 1,379
- `497J` / `497` / `24F-2NT` / `485BPOS` / `485APOS` / `N-CEN` / `N-CSR` /
  `N-CSRS` / `NPORT-P` (registered fund/ETF filings): ~1,700-2,500 each
- `3` / `4` (insider forms — present alongside other forms, hence not
  caught by Ticket 01's pure-ownership-forms-only filter)

Sampled 15 CIKs directly (see session transcript for full rows). They fall
into three clear buckets, none of which is an "operating company" in the
sense `mdm_company` is meant to represent:

1. **Form D private issuers** — one-off Reg D exempt securities offerings
   by private companies/fund SPVs (`Arkane Core Fund One LP`,
   `Series XII - AV Master LLC`, `West Street Infrastructure Partners V
   Offshore (UB) LP`). SEC assigns a CIK once; most never file anything
   else. SEC's CIK registry is permanent and additive (matches this repo's
   own documented "SEC data idempotency" principle for filing artifacts —
   there is no "this startup shut down, remove the CIK" event anywhere in
   the pipeline or in SEC's own system).
2. **13F-HR-only institutional investment managers** — `KAHN BROTHERS GROUP
   INC`, `RIVERBRIDGE PARTNERS LLC`, `Sculptor Capital LP`. These are money
   managers reporting their holdings, not operating companies. MDM already
   has a distinct `adviser` entity type (populated from ADV filings) — a
   13F-only manager without an ADV filing has nowhere else to go today,
   which may be exactly why `run_companies()` was never restricted to
   exclude them.
3. **Registered funds/ETFs** — `VANGUARD WORLD FUND`,
   `FIRST TRUST EXCHANGE-TRADED ALPHADEX FUND II`. These are financial
   instruments, not companies. MDM already has a distinct `fund` entity
   type (populated from ADV private-fund data) that these arguably belong
   under instead, though registered '40 Act funds are a different source
   family from ADV private funds and may need their own entity-type
   decision rather than reusing `mdm_fund` as-is.

(One sampled CIK, `Sohu.com Ltd` / `Robot Consulting Co., Ltd.`, filed
`20-F`/`6-K` — a foreign private issuer's periodic-disclosure equivalent of
`10-K`/`10-Q`/`8-K`. These ARE genuine operating companies; they only
landed in this bucket because the live query's "periodic disclosure" form
list didn't include the foreign-private-issuer forms. A real fix needs to
widen that list, not just exclude everything in this bucket wholesale.)

**Root cause (same shape as Ticket 01, different discriminator):**
`run_companies()` treats any CIK that isn't purely an individual reporting
owner as a company, but SEC's CIK space is broader than "company" in
several more ways beyond individuals — Reg D private issuers, 13F-only
investment managers, and registered '40 Act funds all get their own
permanent CIK and land in `sec_company` the same way a real operating
company does, with no discrimination anywhere in the discovery/tracking/
resolution chain.

**Open questions this ticket needs to resolve before any fix is
implemented (not yet decided):**

1. What is the correct discriminator for "real operating company" here?
   Candidates: expand the periodic-disclosure form allowlist to include
   foreign-private-issuer equivalents (`20-F`, `40-F`, `6-K`) and other
   legitimate non-`10-K` operating-company disclosure forms, then exclude
   any CIK whose *only* forms are Form D / fund-registration / 13F-family
   forms. Needs a validated discriminator the same way Ticket 01 validated
   the ownership-forms-only signal — not yet done.
2. Where should the excluded CIKs actually go? Unlike Ticket 01's
   individuals (who have no MDM entity type at all), these have plausible
   homes: 13F-only managers → `adviser` (needs a decision on whether/how
   to create an adviser entity from a 13F filing alone, absent an ADV
   filing); registered funds → `fund` or a new entity type (needs a
   decision on whether reusing `mdm_fund` — currently ADV-private-fund-
   sourced — is correct, or whether registered '40 Act funds need their
   own type). Simply excluding them from `mdm_company` without deciding
   where they go would silently drop real entities from MDM instead of
   fixing their classification.
3. Is this worth doing before or independent of Ticket 01's still-open
   items (existing-`mdm_company`-row cleanup, `sec_company_sync_state`
   tracking-layer fix, `_derive_is_insider` compounding bug)? A cleanup
   pass for Ticket 01's contamination would need to account for this
   contamination too if both are going to be cleaned up together.

**Status:** root cause and live evidence gathered; discriminator not yet
designed or validated; no fix implemented; scope/destination questions
above need an operator decision before implementation starts.

- [x] Quantify the residual "30K+" gap and confirm it isn't real companies
- [x] Identify the dominant contaminating categories (Form D, 13F-only
      managers, registered funds) via live sampling and a form-type
      histogram
- [ ] Decide the correct discriminator (form allowlist widening +
      exclusion logic), validated against known live examples the way
      Ticket 01's was
- [ ] Decide the destination entity type for 13F-only managers and
      registered funds (not just exclusion — a real classification)
- [ ] Decide sequencing relative to Ticket 01's still-open cleanup/
      tracking-layer/compounding-bug items
- [ ] Implement the fix once the above are decided
