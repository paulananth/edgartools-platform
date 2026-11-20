# 06: Every exposed silver table has its Gold fact

Status: resolved

The operator, 2026-11-20, asked why `nport_holding` and `company_fact` were only in silver: "Why nport_holding and
company_fact just in silver fix the skills". The cause was the Gold skill's over-production rule: an object needed a
named requirement, and only the 13F holdings requirement was approved, so 14 of the 16 exposed silver tables had no
Gold view and (after ticket 05) no mirror. Asked how to change it, the operator chose "Silver spec = requirement
(Recommended)".

## Checklist

- [x] Skill first: data-modeling GOLD.md "No silver table is silver-only" and the over-production row; skill lints pass 2026-11-20 09:41 ET
- [x] Gold makes a fact view from each exposed silver spec (key, links to dimensions, business/event/recorded time, other columns carried); an explicit object wins; `dim_person` and `dim_fund_structure` configured; `tests/unit/test_gold_views.py` 2026-11-20 09:41 ET
- [x] Every spec column the views read exists in the hosted silver tables (information_schema read as the owner: no spec column missing in any of the 16 tables) 2026-11-20 09:41 ET
- [x] Mirror test follows: Gold reads the 2 master tables and the 16 silver tables, 18 in all (`tests/unit/test_exposure_mirror_sql.py`) 2026-11-20 09:41 ET
- [x] `ALTER_MIRROR` added the 14 silver tables back, with `rdm.published_code` of ticket 07, from `mirror_sql.py alter` (operator: "use ANANP11"; words in the approvals log) 2026-11-20 09:52 ET
- [x] Read back: `LIST_MIRRORED_TABLES` shows 19 tables `REPLICATING` (the 18 of this ticket and `rdm.published_code`); row counts equal Postgres in all 19, none differ, 20,092,367 rows 2026-11-20 09:58 ET
- [x] Learning → skill: data-modeling GOLD.md, "No silver table is silver-only" 2026-11-20 10:34 ET
