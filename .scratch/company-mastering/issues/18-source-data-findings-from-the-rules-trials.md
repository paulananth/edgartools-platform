# Source data findings from the rules skill trials

Type: task
Status: open, needs triage (none is fixed here)
Blocked by: none

## Why

Round 1 of the rules skill trials (2026-09-26, `claude/rules-07-skill`,
`.scratch/rules-skill/trials/round-1/`) had two fresh agents onboard SEC
submissions and GLEIF from their captured files. Along the way they found
data problems in today's Company readers. None of them is a skill problem,
and none was fixed in the trial. Each needs a decision: fix, accept, or look
closer. Counts come from the agents' logs; each needs confirming before a
fix.

## Findings, most important first

1. **GLEIF reporting exceptions: a deletion field.** In the 2026-09-11 16:00
   UTC full reporting-exceptions file, `Extension.gleif:Deletion` is present
   on 257,509 records (4.05%), with a JSON `null` value. GLEIF's Golden Copy
   spec uses deletion flags in delta files. `gleif_source.record_evidence`
   ignores `Extension`, so each is kept as a live `reported_parent_exception`.
   **To check first:** whether an empty (`null`) deletion field on a full file
   means anything. If it marks withdrawn exceptions, MDM keeps about 4% of
   exceptions that GLEIF has withdrawn. If it does not, there is nothing to
   fix. (GLEIF log, lines 104-107.)
2. **GLEIF writes the literal text `"NULL"`.**
   - `EntityStatus` is `"NULL"` on 6,687 GENERAL records (9,062 over all
     categories). The mapping keeps it as a value, not as unknown. The name
     rule's eligibility test refuses it anyway.
   - `RelationshipStatus` is `"NULL"` on 345 relationship records. The reader
     refuses them as invalid, which blocks the run.
3. **LEI check digit before scope.** `record_evidence` checks the LEI's
   check digit before it checks the approved Company list. So 356 annulled or
   duplicate LEIs (256 Level 1, 1 relationship, 99 reporting exception) are
   set aside on every full run, whatever the Company list is.
4. **A company dropped as a person.** The warehouse's `is_individual_filer`
   test drops ICONIQ Strategic Partners V TT GP, Ltd. (an organisation) with
   the individual filers, before it becomes a Company record. It was 1 of 21
   dropped in a sample of 40. (SEC log, lines 82-83.)
5. **An address region that is a country code.** ASML's business address
   carries SEC's `stateOrCountry` code `P7` (the Netherlands) as its region.
   (SEC log, lines 92 and 371.)
6. **Every ticker twice.** One catalog run lands both SEC ticker lists, and
   the record builder does not tell them apart, so each filer's tickers repeat
   (Apple: `AAPL, AAPL`). Today this changes no decision: the Company rule
   asks only whether a filer has a ticker, and tickers are not a Company
   field. (SEC log, Q8.)

Also noted (a question, not a defect): 46% of GLEIF relationship records
start at a Fund, and nothing in the repo says how a relationship record links
to a Company.

## Evidence

The two agent logs are on branch `claude/rules-07-skill`:
`.scratch/rules-skill/trials/round-1/sec/rules-log.md` and
`.scratch/rules-skill/trials/round-1/gleif/rules-log.md`.
