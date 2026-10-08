# Cohort slice (profiling ticket 08)

Made by [slice.py](slice.py) on 2026-10-07, 20:44 to 21:00 ET (16 minutes),
from local copies only. Output: `~/.local/share/edgartools/clean-mdm/proving/p08/inputs/`;
`SLICE.json` there holds the sha256 of every file.

| Feed | Taken | Size | Time |
|---|---|---|---|
| SEC submissions | the 500 cohort documents, each checked against the capture's receipt, and the ticker catalog of the same capture | 46 MB | 4 s |
| GLEIF relationships | 2,892 records linking a cohort LEI | 8 MB for all GLEIF | 36 s |
| GLEIF Level 1 | 2,545 records: 222 cohort LEIs, 129 more the Name Census names for cohort names, 2,193 linked by a relationship, 1 successor | (above) | 327 s, then 515 s for the one successor |
| GLEIF reporting exceptions | 2,751 records of those LEIs | (above) | 67 s |
| 13F information tables | 16 tables of 6 cohort filers, of the 999 on this machine | 72 MB | under a second |

Each GLEIF pass checks the archive's sha256, then streams it with a C JSON
parser. The first try used the production verifier (`inspect_archive`),
which hands each of the 3.4 million Level 1 records from the Rust engine to
Python; it was stopped after 20 minutes. The proof's mastering reads GLEIF
through the configured Rust reading, with the cohort's LEIs selected inside
the engine.

Half the time went to a second Level 1 pass for a single successor LEI. A
remake could collect successors in the first pass and accept that one
successor's record is missing, or keep both passes; the slice is made once,
so it was left as is.
