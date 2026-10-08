# Recreation proof (profiling ticket 08)

The proof regenerates today's MDM, RDM and relationships with the skills, in a
sandbox, on the 500-entity cohort ([../cohort](../cohort)), then writes
`DIFF.md`. Only local copies are read (operator, 2026-10-07: "Local feeds only
(Recommended)"); nothing is requested from any provider.

| Step | File | State |
|---|---|---|
| 1. Slice the local feeds to the cohort | [slice.py](slice.py) → `~/.local/share/edgartools/clean-mdm/proving/p08/inputs/SLICE.json` | done (sizes and times in [SLICE.md](SLICE.md)) |
| 2. Rulings file | [rulings.py](rulings.py) → [rulings.jsonl](rulings.jsonl) | done: every recorded operator ruling, verbatim, with ticket and line |
| 3. Sandbox with no answers in it | [sandbox.sh](sandbox.sh) | done: tried at f9c0561f; `still-named.txt` lists what still names a feed |
| 4. Baseline: today's rules mastered on the cohort | not written | **waits for Codex** |
| 5. Cold agent regenerates the rules in the sandbox | not run | **waits for Codex** |
| 6. Sandbox rules mastered with the baseline's script | not written | waits for 4 and 5 |
| 7. DIFF.md | not written | waits for 6 |

## Why steps 4 and 5 wait for Codex

Mastering starts from SEC Company records: a GLEIF record is bound only through
an SEC Company (a name rule or a steward), so a GLEIF-only baseline masters
nothing. Today's SEC Company input is still the retained Company preparation
(`company_source.prepare_company_bundle`, which reads landed Parquet), and
Codex's old-parser retirement is about to retire it: its open item reads
"retire Company preparation/census/provenance" (`.planning/workstreams/sec-configured-fields/TICKET.md`),
and the SEC Company contract still says "pending census, catalog, pagination
and full installed qualification". PR #858 (configured SEC field extraction)
merged on 2026-10-07; it is one step of that work, not the end.

So a baseline can be built today: the cohort's filers are already landed in
ticket 27's work folder, and Company preparation still runs. But it would
measure a path about to be removed, and it would have to be rebuilt once
Company preparation is retired. The cold agent writes SEC source rules in the
shape Codex is still settling. Steps 4 and 6 are one script, and step 7
compares two of its reports, so after Codex merges, the comparison reruns
cheaply. Only step 5, the cold agent, is long. The plan (decision 33) asks
for its time to be estimated and stated before it starts.

## Before the cold agent starts

The sandbox removes answers from the repository copy, but it is not a jail.
The same login can still reach `~/.local/share/edgartools` (ticket 27's
proving runs, the full captures), other local credentials, and the network
through any client that ignores proxy variables. Before launch, the run must
close these (a separate login or container with only the sandbox mounted), or
DIFF.md must state the limit.

## 13F

The 13F information tables are transaction data. They go to silver, which is
ticket 06, so their rows wait for 06. The slice holds the 16 tables (72 MB)
that cohort filers filed, out of the 999 on this machine.
