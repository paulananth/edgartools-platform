# Source data findings from the rules skill trials

Type: task
Status: triaged (operator, 2026-09-29); GLEIF fixes on `claude/company-mastering-18-gleif-blocking`; the SEC fixes (5, 6) next
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

## Triage (Claude, checked against main and the data on 2026-09-29; the operator agreed)

A blocking review left open keeps a run from counting as complete
(`bookkeeping.py`, `unresolved`), which is why findings 2b and 3 were first.

| # | Finding | Checked | Decision |
|---|---|---|---|
| 1 | `gleif:Deletion` on reporting exceptions | 257,509 records, every value `null`, the only field in `Extension`. GLEIF's Golden Copy spec v2.2 (p. 8): "Delta Files … contain the record to be deleted with an added deletion flag in the Extension field"; a deleted record leaves the full file | **Accept.** Guard: a record whose flag holds a value is refused and blocks, so a delta's deletion is never read as live (`native_consumption` accepts delta releases) |
| 2a | `EntityStatus` `"NULL"` | still true | **Accept:** the matching rules refuse it |
| 2b | `RelationshipStatus` `"NULL"` blocks | 345 records; scope is tested before status, and **0** have both ends in scope, even over the 3,584 LEIs the cascade would bind | **Nothing to fix:** the triage overstated it; they are already set aside as out of scope, non-blocking |
| 3 | LEI check digit before scope | still true: 356 invalid LEIs deferred as `invalid_lei` / `invalid_lei_checksum`, which block | **Fix, by the contract:** both reasons non-blocking in all three GLEIF contracts. The Company scope passes the `lei` format when a release is validated (`validate_release`), so an invalid LEI can never be ours; this gives what "scope first" would, with no change to the reading (`gleif-native-record-v1`) |
| 4 | ICONIQ … GP, Ltd. dropped as a person | still true | **Keep as fog** (the capture filter, ticket 05) for the SEC capture work |
| 5 | Region `P7` on ASML's address | still true (`business_address` keeps SEC's code) | **Fix:** a region only for a state or province |
| 6 | Every ticker twice | still true (`_catalog_tickers`) | **Fix:** each ticker once, with 5 |

## Built (GLEIF, 1 and 3)

- `rules/sources/gleif/source.yaml`: `invalid_lei`, `invalid_lei_checksum`
  non-blocking in the three contracts; new contract digests pinned with
  the earlier ones peelable (`test_rules_config_digests.py`).
- `gleif_source.record_evidence`: the deletion guard (`_refuse_deletion`,
  reason `gleif_deletion_flag`, blocking), checked **after** scope, on
  Level 1, relationship and reporting-exception records alike. A delta
  deletes records of every LEI; only one of our Companies' records may
  block, or no delta run could complete (found in review). An `Extension`
  that is not an object fails closed. It changes no reading of the full
  file: its 257,509 flags are all empty.
- Tests: an invalid LEI is non-blocking; an empty flag reads as before; a
  flag with a value is refused and blocks for our Companies' records, and
  stays out of scope for any other, for all three members.
- Applies to new batches only: reviews left open by earlier runs keep their
  blocking disposition.
- Activation: the changed GLEIF source document needs the operator's
  `rules approve` in the Rules Database (the rules skill never approves).

## Review (2026-09-29, three axes)

- Spec: the guard first ran before scope, which would have blocked every
  delta run on deletions of other LEIs; now after scope. Latent, noted: a
  `"NULL"` relationship status still blocks once both ends are ours (0 today).
- Standards: no violations; the `Extension` shape now fails closed.
- GoF: leave it; fold the contract digest layers into `policy_layers` when a
  third one arrives.
