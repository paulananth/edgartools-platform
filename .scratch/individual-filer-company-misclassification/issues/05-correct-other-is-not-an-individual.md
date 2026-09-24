# Correct: SEC entityType "other" is not an individual

Type: task
Status: in progress
Blocked by: none

## Question

Ticket 03/04 of this map treated every SEC `entityType: "other"` filer as an
individual: `sec_company` rows were skipped and `tracking_status` set to
`non_company` on the next fetch. Is that true on real data?

## Measured on bronze (2026-09-24 17:24 ET)

All 76,230 filers in `s3://edgartools-prod-bronze-690839588395/warehouse/bronze/submissions/sec/`,
each read from its latest `main/` file (script: `research/05-scan-bronze-entity-types.py`,
zero SEC requests, 10 minutes). Snowflake was unreachable (every configured
connection points at a suspended trial account), so bronze is the source.

| entityType | filers |
| --- | --- |
| other | 67,421 |
| operating | 7,016 |
| investment | 1,793 |

What the 67,421 "other" filers actually file (recent filings):

| Class | Filers |
| --- | --- |
| Ownership forms only (3/4/5, 144, 13D/G): individuals or holders | 32,989 |
| Private offering issuers (Form D) | 16,259 |
| Funds and investment filers (N-*, 485*, NPORT) | 9,130 |
| Other entity forms | 4,107 |
| 13F institutional managers | 2,949 |
| **Foreign issuers (20-F / 40-F / 6-K)**: Shell, ASML, UBS, Deutsche Bank, BCE, National Grid | **1,516** |
| **Domestic issuers (10-K / 10-Q / 8-K)** | **471** |

1,946 "other" filers carry a ticker; 1,279 of them are foreign issuers.
Only 49% of "other" are individuals. The old rule dropped 1,987 public
companies and about 32,000 other entities.

The 2026-09-12 production export still had Shell and ASML `active`: the rule
(`5ceca106`, 2026-09-10) only fires on a CIK's next fetch, and Shell's newest
bronze file is 2026-07-02, ASML's 2026-06-27.

## Checklist

- [x] Measure the real classification on bronze — (2026-09-24 17:24 ET)
- [x] Replace the rule: an individual is "other" **and** only ownership forms
  **and** no SIC **and** no ticker (`is_individual_filer`); "operating",
  "investment", missing type and empty history stay entities — unit (2026-09-24 17:24 ET)
- [x] ~~Restore a demoted CIK when next fetched~~ removed after review: its
  status before the demotion (deregistered, paused) is unknown, so an
  automatic restore could re-activate it wrongly; restoring is the deferred
  repair below
- [ ] ~~**Restore the already-demoted CIKs.**~~ deferred (operator,
  2026-09-24: v2 is the priority, current production is not). Kept for the
  record: 1,658 entity filers were fetched on
  or after 2026-09-10 and were likely set `non_company`
  (`research/05-likely-demoted-ciks.json`); no sweep fetches a
  `non_company` CIK, so each needs a targeted resync or a one-time repair of
  `sec_company_sync_state`. Needs a live store to confirm which were demoted
- [ ] ~~Their `sec_company` rows were skipped while demoted~~ deferred with
  the restore above
- [ ] **For v2:** Clean MDM's SEC Company contract still maps only
  `operating` to Company (`company_source.py`), so Shell and ASML now reach
  the SEC landing but are set aside by v2 until the SEC classification rule
  (company mastering ticket 03) is activated — tickets 05/06
- [x] Count the new rule itself on bronze: **32,892** of 67,421 "other"
  filers are individuals by `is_individual_filer` (same form list as the
  scan); the ~33K the original map kept out still stay out
- [ ] Note for the map's ticket 02 (re-resolving these as persons): the
  individual class includes holders with no SIC that file only 13D/13G, such
  as some trusts and LLCs; they are entities, not persons
- [x] `/gof-refactor-reviewer` pre-code consult: leave it (one predicate, two
  callers)
- [x] Three-axis `/code-review`: Standards, Spec, GoF
- [ ] PR and CI green
