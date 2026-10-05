# Trial B result: Contoso V2, 10k build

**Result: 52 of 52 lines match, as CSV and as SQLite, and the two forms give
identical findings** (`compare` between them reports no drift). 2026-10-05
07:57 ET.

| Run | Form | Score | Time |
|---|---|---|---|
| 1 | CSV | **48 of 52** ([run1/score.txt](run1/score.txt)) | 8 min |
| final | CSV | 52 of 52 ([csv/score.txt](csv/score.txt)) | 20 s |
| final | SQLite (built by `build_sqlite.py`) | 52 of 52 ([sqlite/score.txt](sqlite/score.txt)) | 18 s |

The answer key ([ANSWER-KEY.md](ANSWER-KEY.md)) and its machine form
([expected.yaml](expected.yaml)) were committed before the first run and were
not changed afterwards.

## What run 1 missed, and the generic change made for each

No change names this data set, its parts or its columns; the genericity lint
still passes on every skill file. Each change applies to any data set.

| Miss in run 1 | Root cause | Change |
|---|---|---|
| orders classed reference (0.714) over transaction (0.667) | Equal-weight tests let a part that points at three other parts pass as reference data | A class's defining test is now **required**: reference data points at no other part; a link part's key is made of links; metadata columns describe data; master, reference and transaction parts have a unique key. A part failing a required test cannot be in that class. "Few parts point at it" became "points at as many parts as point at it" (a header pointed at by its lines is still an event). |
| orders had no event time | Follows from the class: event times are kept only for transaction parts | none needed |
| customer Gender and Title not code lists | Every personal column was kept out of code lists | Only personal columns whose values identify a person (names, addresses, contact details, birth dates) are kept out; a personal code such as a gender is still a code list |
| currencyexchange FromCurrency and ToCurrency not code lists | Every key column was kept out of code lists | Only a single-column key (the part's identity) is kept out; members of a composite key may be codes |

Two more generic changes came from the trial, not from a missed line:

- **Speed.** Run 1 took 8 minutes for 164,000 rows because each query re-read
  the CSV files through a view. Each part is now read once into a table in the
  run's own DuckDB file.
- **Logical types.** SQLite stores dates as text, so the SQLite run reported
  them as text. Each column now reports the logical type a full read proves
  (`type`) next to its stored type (`stored_type`).

## Evidence

- `run1/`: the first run's findings, report and score, kept as they were.
- `csv/` and `sqlite/`: the final findings, reports and scores.
