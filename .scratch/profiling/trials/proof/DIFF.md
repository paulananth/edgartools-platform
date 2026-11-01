# DIFF: today's rules against the cold agent's (ticket 32)

The recreation proof's comparison. **Baseline**: today's rules on `main`
(e606b189, with ticket 09's P5 on the city or postcode), mastered on the
500-entity cohort by `baseline.py`. **Sandbox**: the rules a fresh agent wrote
from the skills alone in a sandbox built at the same commit
(`sandbox.sh`), answering its questions from the 358 rulings. Counts and rule
names only; the pairs, records and both reports stay on the operator's
machine (`~/.local/share/edgartools/clean-mdm/proving/p08/`).

## Result

**A cold agent, resumed once with replayed approvals, recreates a working set of
rules, but not an equal one.** The agent was not fresh for that step: the third run
continued the second agent, in its sandbox, with the skills as #1258 left them. Its
rules master all four parts, and a separate script gets the same counts. They reach
315 of today's 325 Companies and 203 of today's 206 GLEIF links, on a Name Census
that covers only the cohort. The third-run section at the end holds the numbers. The
tables below this line are the first run, when the rules could not be mastered.

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

## Third run, approvals replayed (sandbox at 9f74acc5)

Operator, 2026-10-31: "One more run, approvals replayed". **Not a fresh agent:** the
second run's agent was told to continue (`SendMessage`), with its context and its
`work/` files, for 34 more minutes (10:01-10:35 ET, 2026-11-01). So this shows what
one agent reaches with the skills in two sittings, not what a cold start reaches. It
switched on 7 rules by `approved_by: replayed-ruling`, valid only in the sandbox.

Isolation, over both sittings: 339 of 341 tool calls name the sandbox and the other
2 read its own task output. It also reports two Docker containers and their volumes
(removed), one harness tool-result file and the uv cache, outside the sandbox. The
harness gave it the repository's CLAUDE.md and the operator's memory index, which
the sandbox cannot stop.

The agent's rules were then mastered again by `proof3.py`, not by the agent's
script, from a checkout at 9f74acc5 on fresh stores, with the agent's inputs read
only: 7.6 min, once. `baseline.py` could not run them: its GLEIF step reads today's
file layout and the whole capture, and the agent's census counts its own 500-document
capture. Its counts and writes equal the agent's run (the agent's report kept no digests).

| | Baseline (today's rules) | Sandbox, third run |
|---|---|---|
| Company masters | 325 | 315 |
| Person masters | 50 | 50 |
| GLEIF Level 1 linked to a Company | 206 of 1,577 | 203 of 1,577 |
| Match decisions | 581 | 568 |
| Identifiers on two masters | 0 | 0 |
| Relationships mastered | 0 | 0 |
| GLEIF relationship records staged | 2,257 | 1,943 |
| Second pass changed nothing | yes | yes, Company included (the agent left Company out) |
| Name Census scope | 43,338 filers, 3,428,477 GLEIF records | 500 filers, 2,545 GLEIF records |
| Cascade passes in the census | P5, P6, P7 | P5 |
| Bindings digest | d7ea6ea8ae90 | a8f7c0fc7332 (differs, as the counts do) |
| SEC documents read for Company | 445 of the whole capture | 500, the agent's own capture of the cohort |
| GLEIF input | the published archives, through the configured reading, the cohort's LEIs as its approved scope | the agent's pre-cut JSON Lines files of the same cohort |

What the differences mean:

1. **The census covers only the cohort, and it did not change these links.** The
   sandbox holds only the cohort, so names look rarer than they are: of the 303 names
   its census finds one-to-one, 6 are shared by several filers on the whole population,
   and of its 141 P5 answers, 9 are not P5 there. But none of those reaches a link:
   each of the agent's 203 pairs (its measured pairs, equal to what it bound) stands on
   today's whole-population census with the same LEI, 184 by a one-to-one name and 19
   by P5. Only the name and the pair were checked here, not the jurisdiction or
   postcode the name rules also need. A cohort-only census is still not a way to run
   on real data.
2. **Ten fewer Companies.** The agent's Company step holds back 185 of 500 filers;
   today's holds back 120 of 445. If the 55 filers the baseline does not read for
   Company are all among the agent's held back (assumed, not measured), that is 130
   against 120. The agent rebuilt the classification rule without independent
   labels. Which ten was not read: the baseline's stores are gone.
3. **Relationships are unproved on both sides.** Neither run masters one: no link
   record has both ends bound in this cohort. The agent also staged 314 fewer records,
   and its rules send unsupported types to a different review (1,917 against 968
   `unsupported_identity_kind`; the baseline has 1,683 `unsupported_relationship_type`).
4. **The agent's 37 unexplained reviews are explained.** They are `unresolved_endpoint`
   reviews: relationship records waiting for a missing end (read on the stores: 1,374,
   547, 88, 37 and 1,917 sum to 3,963). The run report's review counts leave that reason out.
5. **What the replay stands on.** No record or pair was labelled: each proof's
   `correct` repeats its `n` on a replayed ruling's authority, so the 7 switch-ons show
   the rules run, not that they are right. The Person proof carries a ruling's 841
   people; on this cohort's 50 its bound is 0.928, under its 0.99 bar. It has no
   registered-agent check. 12 of its 44 questions stayed unanswered, and it has no
   lasting Rules or RDM database.

Not run: P6 and P7 (the agent did not declare them), a census built from its rules over the whole population, and a cold start with the fixed skills that goes past the second run.
