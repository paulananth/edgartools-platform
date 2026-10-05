# Trial A result: SEC submissions and GLEIF golden copies

**Result: 38 of 41.** The only misses are three record keys where the data
disagrees with the answer key. Each one is explained below with its evidence.
The answer key ([ANSWER-KEY.md](ANSWER-KEY.md), [expected.yaml](expected.yaml))
was committed before any profiling code and was not changed afterwards. Local
copies only: no request to any provider.

| Run | Score | Time |
|---|---|---|
| 1 | 30 of 41 ([run1/score.txt](run1/score.txt)) | not recorded |
| 2 | 34 of 41 ([run2/score.txt](run2/score.txt)) | not recorded |
| 3 | 37 of 41 ([run3/score.txt](run3/score.txt)) | 51 min |
| final | 38 of 41 ([final/score.txt](final/score.txt)) | 56 min |

Most of each run is the large entity file: 12.3 GB is over the 5 GB limit, so
the run reads a seeded sample of 100,000 records, says so with its time
estimate, then makes full passes to confirm the key candidates (`scan:
sampled`; the `LEI` key is confirmed on every record).

The scorer matches a column name by its last dotted parts
(`RelationshipRecord.Relationship.StartNode.NodeID` matches
`StartNode.NodeID`), because the answer key writes short paths.

## Misses where the data disagrees with the answer key

These are reported as found. The skill's answer is the correct one for this
data, so the skill was not changed to match the answer key.

| Part | Answer key | Found | Evidence |
|---|---|---|---|
| submissions.filings.recent | `accessionNumber` | (`cik`, `accessionNumber`) | 8,065,661 rows but 6,750,027 distinct accession numbers (unique 0.837). One filing with several filers is listed in each filer's file, so the number repeats across parents. It is unique within each parent, so the parent key plus it is the key. |
| submissions.tickers | (`cik`, position) | (`cik`, `value`) | All 9,528 values are distinct and none repeats within a parent. A key found in the data comes before a designed one (a position), and it survives a reordered list. |
| rr | (`StartNode.NodeID`, `EndNode.NodeID`, `RelationshipType`) | (`StartNode.NodeID`, `RelationshipType`) | The two columns are already unique on all 487,721 rows: a start node has at most one end node per relationship type. The key is the smallest unique set, so `EndNode.NodeID` is not in it. It is still a link and still a hierarchy end. |

## What earlier runs missed, and the generic change made for each

No change names this data set, its parts or its columns. The genericity lint
still passes on every skill file.

| Miss | Root cause | Change |
|---|---|---|
| Two attempts crashed before run 1 finished | One date column with two timestamp formats failed a whole load; a child list's parent was looked up by name | A column that does not read as a date falls back to text; a child part finds its real enclosing parent |
| submissions, tickers list, former names classed unknown | A list of one written as an object made a separate part; personal-word tests read an address part as people | A list of one moves into its child part; "first" and "last" mean a person only next to "name"; contact words count in any part |
| tickers.`cik` → submissions.`cik` not found | Zero-padded text against integers | Inclusion compares such columns as numbers |
| rr classed transaction, so its links were "separate" | The relationship test wanted every key column to be a link, and counted every column as an attribute | A link part's key may be one end plus a role; attributes exclude codes, dates and constant columns |
| filings.recent key not unique | An accession number repeats across parents | A key unique within the parent (parent key plus the column) |
| rr hierarchy not found (run 3) | The two ends came in link order, so the parent was read as the child | The end inside the record key is the child; checked on the full file: six hierarchies, one per relationship type |

Run 1 also showed two speed problems, fixed generically: streaming a large JSON
array was quadratic (now linear, 100,000 records in 8 s), and key confirmation
inserted values row by row (now one statement, 3 million values in 8 s). A
stopped run now removes its working copy, and long runs go through `caffeinate`
so the computer does not sleep.

## Evidence

- `run1/`, `run2/`, `run3/`: each run's findings, report and score, kept as
  they were.
- `final/`: the final findings, report and score.
