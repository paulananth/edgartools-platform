# Ticket 09 — every trial question, classified

Each question number is the one in that round's `TRIAL-LOG.md`.
- **Gap** means a spec gap. It is fixed in `docs/specs/source-contract/spec.md`, at the section named.
- **Lag** means runner lag: the prototype was behind the spec (see `expected-runner-lag.md`). A lag is fixed in the runner and does not become a spec rule.
- **Answered** means the spec already said it, and the agent confirmed by trying.

## Round 1 — SEC company profiles (17 questions: 14 gaps, 1 lag, 2 answered; Q4 also exposed lag L5)

| Q | Topic | Class | Fix |
|---|---|---|---|
| 1 | one JSON document per file | Gap | §8.1 json row |
| 2 | plain JSON scalars have no `$` | Gap | §8.2 |
| 3 | `$` on a list of strings silently read `""` | Gap | §8.2, and now an error |
| 4 | unmapped kind: no metric, unknown `deferred:` limit ignored | Gap + Lag L5 | §16 closed limit names; §13.4 deferred rows; the runner now counts `deferred` |
| 5 | §13.4 rejects `kind_values` over `entityType`, but the task asks for it | Gap | §13.4 company-source trap |
| 6 | identifier namespace vs format | Gap | §13.1 identifiers |
| 7 | how a new source wins fields | Gap | §13.2a |
| 8 | free-text Dataset Contract parts | Gap | §13.3 table |
| 9 | `null` in `pattern`/`in_set` | Gap | §14 |
| 10 | fixture with several documents | Gap | §15 fixture lists |
| 11 | how a call with no arguments is written | Gap | §8.5 |
| 12 | custom check wiring, module name | Answered | §11 |
| 13 | no gate still printed "proven" | Lag L11 | runner fixed; §4.2 now says it outright |
| 14 | is `collapse` required | Answered | §12, Open §25 item 6 |
| 15 | former names: a joined column or dated child rows | Gap | §12 extra tables |
| 16 | `rows` floor for a growing family | Gap | §16 |
| 17 | form of `field_shape` | Gap | §13.1 |

## Round 2 — SEC company profiles, a new agent (13 questions: 9 gaps, 4 answered)

| Q | Topic | Class | Fix |
|---|---|---|---|
| 1 | a deferred row in `expect.mdm` | Gap | §15 `{ deferred: <reason> }` |
| 2 | joined column vs child table | Answered | §12 |
| 3 | a child table's parent key | Gap | §12 example with `from: document`; the Mapping Document marks it |
| 4 | is `completeness` allowed | Gap | §13.3 |
| 5 | the worked example authors `registry_evidence` | Gap | §22 example corrected |
| 6 | value vocabularies (SEC state codes vs GLEIF jurisdictions) | Gap | §13.2a same-meaning rule |
| 7 | the base of `max_pct` for `deferred` | Answered | §16 |
| 8 | check names collide across tables | Gap | §14 `label:` |
| 9 | `.` on plain strings, `count` without `default` | Answered | §8.2, §9 |
| 10 | what `timestamp` accepts | Gap | §9, §12 |
| 11 | `given.identities.record` with a padded CIK | Gap | §15 |
| 12 | is a merge case worth writing | Answered | §15 |
| 13 | `effective_time: unknown` vs a policy the author cannot edit | Gap | §13.3 |

## Round 3 — SEC Form ADV advisers, CSV (14 questions: 8 gaps, 1 lag, 5 answered)

| Q | Topic | Class | Fix |
|---|---|---|---|
| 1 | non-ISO dates | Gap | §9 `date_format` (proposed) |
| 2 | what a `date` column accepts | Gap | §12 |
| 3 | an empty CSV cell | Gap | §8.1 |
| 4 | the CRD namespace and format | Gap | §13.1 |
| 5 | one row per filing vs a repeated record key | Gap | §13.2: one record key per publication (proposed), found in review from `023_clean_mdm.sql:50` |
| 6 | country names vs ISO codes | Answered | §13.2a |
| 7 | map `name` when it is unranked | Answered | §13.2a |
| 8 | `family` for a new provider | Gap | §13.3 |
| 9 | `evidence_only` accepted but not checked | Lag | runner checks it; the schema now closes `expect` entries (§15, §9.1) |
| 10 | `each: "."` over CSV rows | Answered | §8.4 |
| 11 | does a check need an explicit limit | Answered | §16 |
| 12 | the Custom Step import | Answered | §11 |
| 13 | how to cut a CSV fixture | Gap | §15 (the `SYNTHETIC` rule is proposed) |
| 14 | how merge cases find Docker | Gap | §15 |

## Runner lags and where each came from

| Lag | Found by |
|---|---|
| L11: no gate still printed "proven" | round 1 Q13 |
| L5: `deferred` not counted | round 1 Q4 |
| unknown gate limit names silently ignored | round 1 Q4 |
| `evidence_only` not checked | round 3 Q9 |
| L10: a missing fixture gave a traceback | the setup, before round 1 |

Three more runner bugs were found by the review of this ticket, not by a
trial agent. All are fixed:
- `--gate` on a contract with no gate crashed;
- `$` on one bad record aborted the whole run;
- bad CSV settings exited as engine bugs (exit 3).
