# 04 Capture the cohort's company facts

Priority: 36, tier 3, product value. Map: [Rebuild priorities](../map.md). Moved from `.scratch/company-financials/issues/04-capture-the-cohorts-company-facts.md` on 2026-10-13; a Blocked by list of numbers now uses this map's numbers (or names the old effort); free text keeps the old effort's numbers.

Type: task. Status: resolved. Blocked by: 34. Map: [map](../../company-financials/map.md).

## Question

Capture company facts for the proof cohort (the 500 fixed entities, `.scratch/profiling` cohort list) by the route ticket 02 decides, into the local proving folder with each file's sha256; record counts, sizes, companies with no facts, and the elapsed time.

## Answer

Done 2026-10-12 07:57 ET (6 minutes, 07:51 to 07:57 ET; `capture/capture_company_facts.py`, 5 requests a second): 500 cohort CIKs asked; 368 have company facts, 132 have none (404); 773 MB raw, 49 MB gzipped, in `~/.local/share/edgartools/clean-mdm/proving/company-facts/cohort/` (local, not committed) with `CAPTURE.json` naming each CIK's status, raw bytes, sha256 and fetch time. No 403 or 429.

Long form for profiling (2026-10-12 08:05 ET, 1 min 43 s; `capture/to_facts_parquet.py`, local `company-facts/cohort-long/`, 32 MB): 5,134,979 facts, 8,495 concepts, 329 companies with facts; 39 of the 368 captured documents hold no facts (one was an empty `{}`).
