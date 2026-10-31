# DIFF: today's rules against the cold agent's (ticket 32)

The recreation proof's comparison. **Baseline**: today's rules on `main`
(e606b189, with ticket 09's P5 on the city or postcode), mastered on the
500-entity cohort by `baseline.py`. **Sandbox**: the rules a fresh agent wrote
from the skills alone in a sandbox built at the same commit
(`sandbox.sh`), answering its questions from the 358 rulings. Counts and rule
names only; the pairs, records and both reports stay on the operator's
machine (`~/.local/share/edgartools/clean-mdm/proving/p08/`).

## Result

**The skills alone do not recreate today's rules.** The sandbox's rules pass
`rules check` for every source, but they cannot be mastered: the run stops at
its first step, and even past it no GLEIF record would join an SEC Company.
Each gap below is a place the skills do not say what today's rules do.

## Mastering

| | Baseline | Sandbox |
|---|---|---|
| Ran on the cohort | yes, 24 min, once | no: stops at once (no `bookkeeping` section in any source file) |
| Company masters | 325 | not run (the agent's own reading: 373 Company records, 127 held back) |
| Person masters | 50 | not run (agent: 50 Person records) |
| GLEIF Level 1 linked to a Company | 206 of 1,577 | not run; by its rules none can link (see "Matching") |
| Relationships | 0 of 574 consolidation records (both ends must be Companies; the cohort's parents are not cohort filers) | not run (agent: 1,943 parent links read, none could attach) |
| Second pass changed nothing | yes (every digest equal) | not run |
| Identifiers on two masters | 0 | not run |

The baseline's relationship count is 0, so this cohort does not exercise
relationships for either side.

## Rules, file by file

In scope (SEC Company and Person, GLEIF Level 1 and relationships, the RDM
code sets): the sandbox wrote 25 files, today's `main` holds 152 (the other
feeds account for most of the difference and are out of scope).

| Part | Matched | Today has, the sandbox lacks | The sandbox has, today lacks |
|---|---|---|---|
| Dataset Contracts | the four codes (`sec.submissions.company.v1`, `sec.submissions.person.v1`, `gleif.level1.v1`, `gleif.relationships.v1`); the record keys; CIK and LEI as identifiers | `gleif.reporting_exceptions.v1` (out of the task); the adapters' `provenance`; GLEIF's `native_member` and the control columns (category, deletion, relationship ends) | Company's lookup-only cross-references (EIN, SEC's LEI) as `cross_references` |
| Source files | `source`, `bronze`, `read`, `execution`, `mdm` sections | **`bookkeeping`** (the targets that run and master a feed) in all three; `acquisition`; SEC Company's 13 reading files (census, catalog, main, name key) and GLEIF's 18 (census readings, name key, Level 1 and relationship readings) | `gleif/relationships-jsonl.yaml` |
| Company rules | `sec-company-candidate`, `company-cik` | the two name rules (`sec-gleif-name-jurisdiction`, `-postal`), the cascade (P5, P6, P7); rules of other feeds (N-PORT, Form ADV, GLEIF issuer: out of scope) | `company-lei` (waits for a Company already holding the LEI) |
| Person rules | `sec-person-candidate`, `person-cik` | the ownership feed's two rules (out of scope) | none |
| Kind settings | bars, defaults, identifiers, lists | `normalizers` and `version` on both kinds; Company's `bd_number` and `crd` identifiers (Form ADV, out of scope) | `defaults.clear_sources` |
| Policy | | 22 switched-on rules with their proofs | none switched on (approvals were the operator's) |
| RDM | `mdm-relationship-types` and `sec-place-codes` as code sets | today's pinned versions (10 sets, 309 place codes) | its own first versions: 3 relationship types, 61 place codes |

## Why each gap (the skill to fix)

1. **No `bookkeeping` section**: data-onboarding says it "belongs to the
   Bookkeeping skill", and nothing sends the agent there to write one, so the
   rules have no target to run. Fix: data-onboarding's last steps hand off to
   the bookkeeping skill with what a mastering target must hold.
2. **No GLEIF-to-SEC matching**: the name rules need the Name Census (a name
   count over both whole sources) and a measured proof; the skills describe
   name matching as a last resort and refining-rules work, and give no recipe
   for the census readings, so the agent stopped (question 16, unanswered).
   Fix: a skill section on SEC-to-GLEIF matching with the census readings
   and the cascade, or the recipe in refining-rules.
3. **The SEC Company code needs its classification rule switched on and the
   census files**: these are platform facts no skill states. Fix: state them
   where the skill describes the Company feed.
4. **Approvals**: 11 of 36 questions unanswered, all approvals or choices no
   recorded ruling covers (stand-ins on GLEIF, SEC place codes, EIN zeros);
   the standing ruling "Approved the rules always" is not in the rulings
   file. Fix: add it (and the other standing rulings in CLAUDE.md) to
   `rulings.py`'s sources.

## Isolation (the sandbox is not a jail)

The agent ran as the operator's login. Every command it ran named the
sandbox, and its file tools touched nothing outside it (audit of its tool
calls). Its own log lists three early touches: a failed build's log written
one folder above the sandbox (moved in at once), a listing of the parent
folder's names, and one command started from the main checkout's Python,
which failed before reading data. The harness may also have given it the
repository's guides; that cannot be audited.

## Not covered

N-PORT, OpenFIGI, Form ADV (operator, 2026-10-29: "Keep the 10-07 scope"),
GLEIF reporting exceptions, and the 13F rows (silver, ticket 06).

## Second run, after the skills were fixed (sandbox at 9f74acc5)

The three skill gaps were fixed (#1258) and the rulings file grew to 909
(CLAUDE.md's standing rulings added). A new fresh agent, 32 minutes
(06:28-07:00 ET, 2026-10-31); every one of its 176 tool calls stayed in the
sandbox, but the harness gave it the repository's CLAUDE.md and the
operator's memory index, which the sandbox cannot stop.

| | First run | Second run |
|---|---|---|
| `rules check` | passes | passes |
| Run definitions (`bookkeeping` mastering targets) | none | all four, each writing its input manifest offline |
| Registers on the stores (policy, four contracts) | not reached | yes |
| Mastering on the cohort (sample) | stops at once (no target) | stops at Company preparation: nothing is switched on, and the Company chain reads its switched-on classification rule |
| SEC Company / Person (its own reading) | 373 / 50 | 315 / 50 (145 held back, 40 undetermined) |
| GLEIF Level 1 Companies; consolidation links | 1,577; 1,943 | 1,577; 1,943 |
| SEC-to-GLEIF matching | none | none: it found 165 one-to-one exact-name pairs but built no Name Census, judging a binding rule out of reach without a measured proof |
| Questions: answered by rulings / unanswered | 22 / 11 of 36 | 19 / 11 of 30 |

What stays out of reach of the skills alone, and why:
1. **Switch-on.** Every rule version the agent writes is new, so no recorded
   approval covers it, and its proofs need labels only the operator gives
   (the Person bar needs 381 people; the cohort has 50). This is by design:
   approvals are the operator's.
2. **Name matching.** With the recipe in refining-rules, the agent still
   stopped before building the census, since the rule it feeds cannot be
   switched on without labels (point 1).
3. **Two platform faults** it found:
   - the MDM merge workers load the Company census reading
     (`census-filer.yaml`) for every source, so a rules folder without it
     cannot merge anything;
   - the cohort slice is not in the capture layout the reader expects (the
     proof's slice, not the platform).
