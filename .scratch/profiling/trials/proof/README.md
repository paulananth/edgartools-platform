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
nothing. Today's SEC reading into MDM is the part Codex's old-parser
retirement is replacing:

- the landing path the earlier Proving Runs used (`SilverLandingStore`,
  company mastering ticket 27) is deleted from main;
- the configured path (`source.read` → `source.combine` → `mdm.prepare`) is
  "locally qualified only", and the SEC Company target still waits on its
  census, catalog and pagination integration (`rules/sources/sec.submissions.company/source.yaml`);
- Codex's open PR #858 replaces the SEC Company and Person field extraction.

The cold agent writes SEC source rules in the same shape, so it waits for that
design too. Steps 4 and 6 are one script, and step 7 compares two of its
reports, so after Codex merges, the comparison reruns cheaply. Only step 5, the
cold agent, is long. The plan (decision 33) asks for its time to be estimated
and stated before it starts.

## 13F

The 13F information tables are transaction data. They go to silver, which is
ticket 06, so their rows wait for 06. The slice holds the 16 tables (75 MB)
that cohort filers filed, out of the 999 on this machine.
