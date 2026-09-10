Type: research
Status: resolved

## Question

While extending mdm-relationship-versioning-gap's quarantine backfill to
COMPANY_HOLDS (Ticket 10 there), a dry-run showed one relationship_id with
27,849 history rows -- wildly out of scale versus anything seen in
INSTITUTIONAL_HOLDS. What is this, how widespread is it, and where does
it come from?

## Answer

The three largest COMPANY_HOLDS relationship_ids by row count all trace
to the same shape: a well-known individual, misresolved as a `company`
entity instead of a `person`.

| relationship_id | rows | "company" name | CIK | real identity |
|---|---|---|---|---|
| a699c00c-66a9-a542-5d5a-e860e66e49b9 | 27,849 | Zuckerberg Mark | 1548760 | Meta insider |
| 4837091c-6a46-c522-6ec7-1d4e6db7f416 | 4,103 | HUANG JEN HSUN | 1197649 | NVIDIA insider |
| 118d6850-30ea-5ad0-2770-2ac03a1e0427 | 2,910 | Olivan Javier | 1564475 | Meta insider |

Confirmed live against `EDGARTOOLS_PROD.EDGARTOOLS_SILVER.SEC_COMPANY_FILING`
for all three CIKs: filing history is exclusively `3`/`4`/`5`/`144`/
`SC 13G`/`SC 13G/A` -- zero `10-K`/`10-Q`/`8-K`/any genuine issuer filing
type. None of the three appear in SEC's real, live `company_tickers.json`
(fetched directly, 10,407 entries) -- ruling out the standard
ticker-based `seed-universe` path as the source.

`EDGARTOOLS_SILVER.SEC_COMPANY.ENTITY_TYPE` for all three is `'other'` --
SEC's own submissions data already correctly distinguishes these from
real operating companies (`'operating'`)/investment vehicles
(`'investment'`). The signal exists in the data; nothing reads it as a
filter.

**Blast radius** (live query against `SEC_COMPANY`):

| entity_type | count |
|---|---|
| other | 64,924 |
| operating | 7,009 |
| investment | 1,758 |

Of the 64,924 `entity_type='other'` rows, 32,948 have a filing history
that is *exclusively* ownership/144/13D/13G forms -- confirmed individual
filers, not companies. That is ~4.5x the real, legitimate operating-company
count and ~45% of the entire `sec_company` table.

**Confirmed write path, not yet confirmed discovery path:** `merge_company()`
(`edgar_warehouse/silver_store.py`) is the sole writer of `sec_company` and
applies zero filtering on `entity_type` -- it writes whatever
`stage_company_loader` (`edgar_warehouse/loaders/bronze_submission_extractors.py`)
hands it. `stage_company_loader` correctly carries SEC's `entityType`
field through into the `entity_type` column, but that value is captured
and stored, never consulted anywhere to gate the write. This confirms
*where* the missing filter belongs (either at `stage_company_loader`/
`merge_company`, or earlier), but not yet *which upstream caller* first
decided these individual CIKs were worth fetching a full submissions.json
for in the first place -- that requires tracing `daily_incremental`'s
daily-index "impacted CIK" discovery (the leading candidate, since SEC's
daily index lists an ownership-form accession under both the issuer's and
every reporting owner's own CIK) and/or `bootstrap-next`/`load_history`'s
CIK-discovery logic. Left as the map's first "Not yet specified" item
rather than guessed at.

**Consequence for the parent map:** mdm-relationship-versioning-gap's
Ticket 10 is proceeding with HOLDS/EMPLOYED_BY/IS_INSIDER (confirmed clean
at this same live-diagnostic pass -- their max rows-per-relationship_id
are 676/31/179 respectively, normal scale) but pausing on COMPANY_HOLDS
until this map's fix + cleanup strategy are decided. Backfilling
COMPANY_HOLDS' quarantine flags now would resolve conflicts sitting on top
of this contamination, making it look clean instead of fixing it.
