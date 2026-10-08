# How much of the goal Claude and Codex have completed

Read 2026-10-08 18:09 EDT on `origin/main` `0899b2386f25d2ee8bf8b0dc14ca28d70a6d0a13` (PR #874). This file is the measurement. It changes no ticket, rule, or source file.

An earlier draft of this note was taken at 06:46 EDT on `862a1e66`. After that, #866, #867, #868, and #869 through #874 merged. This revision replaces that draft.

The primary checkout `/Users/aneenaananth/projects/edgartools-platform` is still `main` at `a60ba016` and was not fast-forwarded. Its short status is still only `.planning/workstreams/fix-pipelines/STATE.md` (modified) and `infra/aws-prod-application.json.bak-20260915-predeploy` (untracked).

## The two goals

These are different ends. A checkbox count on one does not finish the other.

- **Profiling program (Claude).** `.scratch/profiling/map.md:5` says the program ends when the operator accepts the recreation proof's `DIFF.md`. `.scratch/profiling/map.md:10` still says phase B starts after Codex's old-parser retirement goal is merged.
- **Old-parser retirement (Codex).** The tickets that carry the goal still leave the same gate open: an installed empty-store population of 6,414 Companies and 3,052 CIK+LEI bindings, unchanged replay and recovery, then removal of the old parsers and parent L3–L8. See `.planning/workstreams/sec-configured-fields/TICKET.md:9` and `.planning/workstreams/company-main-retirement/TICKET.md:11`.

Handoff #860 is the seam list between those goals. It is not either goal. Every item in that list is now on `origin/main`.

## Handoff #860

| Item | Owner | On `origin/main` |
|---|---|---|
| C1 | Claude | Done. `.scratch/profiling/issues/02-rdm-database.md:19` stays struck and names merge `716cb999418d47f82acc2412021f62d4c724d8ce`. PR #862, `4840c6ba`. |
| C2 | Claude | Done. `.scratch/profiling/issues/08-recreation-proof.md:22` names `.scratch/profiling/trials/proof/rulings.jsonl`, 358 rulings, each marked replayed and valid only in the sandbox. PR #863, `4a673ec6`. |
| C3 | Claude | Done. `.scratch/profiling/issues/02-rdm-database.md:35` is checked. `edgar_warehouse/mdm/clean/quality.py:121` reads the published pin. `edgar_warehouse/mdm/clean/quality.py:128` loads `files.reference_pin`. `rules/sources/sec.submissions.company/quality.yaml:75` is `36270dc9e924128f1338ecee2fd4684f2c13b35303e634f49fabae9213759f00`. `rules/reference/sec-place-codes.yaml` is gone. PR #862. |
| J1 | Operator, then both | Done on both sides. `.scratch/profiling/issues/07b-name-based-matching.md:34` quotes the operator, 2026-10-08 06:19 ET: "Proven name rules may bind (Recommended)". `name_census_match@1` may bind when the name is unique on both sides and a second fact agrees. `name_id@1` stays lookup only. Codex recorded the same words at `.scratch/company-mastering/issues/08-qualify-sec-to-gleif-fuzzy-binding.md:275`. PRs #865 and #866. |
| X1 | Codex | Done. `.scratch/profiling/issues/02-rdm-database.md:32` is checked. `rules/sources/sec.submissions.company/source.yaml:654` opens `reference_pins:`, `rules/sources/sec.submissions.company/source.yaml:656` is `code_set: sec-place-codes`, and `rules/sources/sec.submissions.company/source.yaml:658` is sha256 `36270dc9…`. The inline rows remain: `rules/sources/sec.submissions.company/source.yaml:661` is `AL:` and `rules/sources/sec.submissions.company/source.yaml:1585` is `XX:`. PR #866, `4392159e`. |
| X2 | Codex | Done. `.planning/workstreams/gleif-member-contracts/TICKET.md:56` and `.planning/workstreams/gleif-member-contracts/TICKET.md:66` are checked and cite the six completed reports on census-evidence line 18. PR #866. |
| X3 | Codex | Done. `.planning/workstreams/company-configured-preparation/TICKET.md:10`, `.planning/workstreams/company-configured-preparation/TICKET.md:17`, and `.planning/workstreams/company-configured-preparation/TICKET.md:26` are checked, and line 17 names merge `b0b406468079a62dfc1aad53245f8d31d203acb4`. `.planning/workstreams/gleif-configured-reading/TICKET.md:9` and `.planning/workstreams/gleif-configured-reading/TICKET.md:10` are checked and cite #834, #841, and #843. PR #866. |

## Profiling program

`.scratch/profiling/map.md` now has 18 ticket rows. Two rows were added after the morning draft: 01d and 05b.

Done on the map: 00 (`.scratch/profiling/map.md:18`), 01, 01a, 01b, 01c, 03, 04, 04b, 04c, 05b (`.scratch/profiling/map.md:30`, #868), and 07b (`.scratch/profiling/map.md:33`). That is 11 rows. Ticket 02 (`.scratch/profiling/map.md:24`) is also finished as checklist work: the contract pin is checked at `.scratch/profiling/issues/02-rdm-database.md:32`.

Partial or open:

- Ticket 01d (`.scratch/profiling/map.md:23`) is open. Its measured parts are merged: drift #869, level tables #871, two deliveries #872, `in_hierarchy@1` #873, and the generic skills edit #874. `.scratch/profiling/issues/01d-profiling-follow-ups.md:26` stays a struck deferral of `skills/data-platform/READING.md` and `COMBINING.md`. `.scratch/profiling/issues/01d-profiling-follow-ups.md:27` is still unchecked.
- Ticket 05 (`.scratch/profiling/map.md:29`). MDM and RDM are done. `.scratch/profiling/issues/05-agent-context-views-and-command.md:27` (`silver.table_context`) stays open because ticket 06 has not started. `.scratch/profiling/issues/05-agent-context-views-and-command.md:30` (`mdm migrate` for 005, 006, and 007) is also still open. Ticket 05b closed the separate `--as-at` follow-up.
- Ticket 08 (`.scratch/profiling/map.md:35`). Cohort, slice, rulings file, sandbox, and the C2 replay are checked through `.scratch/profiling/issues/08-recreation-proof.md:22`. Still open: the cold agent's use of the rulings (line 23), sandbox mastering (line 24), the configured GLEIF read for the baseline (line 25), `.scratch/profiling/issues/08-recreation-proof.md:26` (`DIFF.md`), review and merge (line 29), and `.scratch/profiling/issues/08-recreation-proof.md:30` (operator acceptance). The baseline and the cold agent stay struck, waiting on Codex. No `DIFF.md` exists under `.scratch/profiling/`.

Not started: ticket 06 (`.scratch/profiling/map.md:31`), ticket 07 (`.scratch/profiling/map.md:32`), and ticket 07c (`.scratch/profiling/map.md:34`). Tickets 06 and 07 stay blocked by the retirement gate on `.scratch/profiling/map.md:10`.

The profiling destination is not met. Phase A is done except the two remaining 01d lines. Phase B has the RDM work and the start of the proof. The proof's baseline and cold agent are waiting on Codex's retirement of Company preparation.

## Old-parser retirement

The shared gate is still open. These lines on `origin/main` each still require the 6,414 / 3,052 installed population, or the parser deletion that follows it:

- `.planning/workstreams/company-main-retirement/TICKET.md:9` and `.planning/workstreams/company-main-retirement/TICKET.md:11`
- `.planning/workstreams/company-census-evidence/TICKET.md:13` and `.planning/workstreams/company-census-evidence/TICKET.md:14`
- `.planning/workstreams/gleif-configured-fields/TICKET.md:10`
- `.planning/workstreams/sec-configured-fields/TICKET.md:9`
- `.planning/workstreams/company-address/TICKET.md:12`
- `.planning/workstreams/gleif-configured-reading/TICKET.md:13`
- `.planning/workstreams/gleif-member-contracts/TICKET.md:10`

Merged building blocks, which do not close that gate:

- #846 (`3da078f8`) configured Company and GLEIF name-census keys.
- #844 (`b0b40646`) bundled Company preparation.
- #854 (`f56f8548`) qualified pinned census evidence.
- #857 (`220b8a49`) replaced GLEIF field extraction.
- #858 (`f9c0561f`) replaced SEC Company and Person field extraction.
- #864 (`0b2f7c12`) retired the handwritten Company address derivation.
- #866 (`4392159e`) pinned the place rows and closed handover X1, X2, X3, and Codex's J1 note.
- #867 (`dec6c867`) retired census name extraction through bundled Rules. Census lines 13 and 14 stay open.

## Where that leaves the work

Claude has finished phase A except ticket 01d's two remaining lines, and has finished every Claude action in handover #860, including J1. The profiling program itself is short of its end: `DIFF.md` is not written and the operator has not accepted it. Tickets 06, 07, and 07c have not started.

Codex has finished every Codex action in handover #860. The retirement goal those tickets name is not complete. The 6,414 / 3,052 installed population, replay, recovery, and old-parser deletion are still open.

## Citation index

Each row is `path:line | substring of that line` on `0899b238`.

- .scratch/profiling/map.md:5 | DIFF.md is accepted by the operator
- .scratch/profiling/map.md:10 | phase B starts after Codex's old-parser retirement goal is merged
- .scratch/profiling/map.md:18 | done (#823)
- .scratch/profiling/map.md:23 | 01d-profiling-follow-ups.md
- .scratch/profiling/map.md:24 | contract-embedded rows pinned (Codex #866)
- .scratch/profiling/map.md:29 | silver waits for 06
- .scratch/profiling/map.md:30 | done (#868)
- .scratch/profiling/map.md:31 | 06-silver-writer.md
- .scratch/profiling/map.md:32 | 07-readers-per-feed.md
- .scratch/profiling/map.md:33 | done (#838)
- .scratch/profiling/map.md:34 | 07c-unstructured-extraction.md
- .scratch/profiling/map.md:35 | baseline and cold agent wait for Codex's retirement
- .scratch/profiling/issues/02-rdm-database.md:19 | 716cb999418d47f82acc2412021f62d4c724d8ce
- .scratch/profiling/issues/02-rdm-database.md:32 | reference_pins.places
- .scratch/profiling/issues/02-rdm-database.md:35 | YAML removed
- .scratch/profiling/issues/07b-name-based-matching.md:34 | Proven name rules may bind
- .scratch/profiling/issues/01d-profiling-follow-ups.md:26 | READING and COMBINING
- .scratch/profiling/issues/01d-profiling-follow-ups.md:27 | Skills: PR, CI, merge
- .scratch/profiling/issues/08-recreation-proof.md:22 | rulings.jsonl
- .scratch/profiling/issues/08-recreation-proof.md:26 | DIFF.md: every line matched or explained
- .scratch/profiling/issues/08-recreation-proof.md:30 | Operator accepts
- .scratch/profiling/issues/05-agent-context-views-and-command.md:27 | silver.table_context
- .scratch/profiling/issues/05-agent-context-views-and-command.md:30 | mdm migrate
- .scratch/company-mastering/issues/08-qualify-sec-to-gleif-fuzzy-binding.md:275 | Proven name rules may bind
- edgar_warehouse/mdm/clean/quality.py:121 | def _reference_keys
- edgar_warehouse/mdm/clean/quality.py:128 | files.reference_pin
- rules/sources/sec.submissions.company/quality.yaml:75 | 36270dc9e924128f1338ecee2fd4684f2c13b35303e634f49fabae9213759f00
- rules/sources/sec.submissions.company/source.yaml:654 | reference_pins:
- rules/sources/sec.submissions.company/source.yaml:656 | code_set: sec-place-codes
- rules/sources/sec.submissions.company/source.yaml:658 | 36270dc9e924128f1338ecee2fd4684f2c13b35303e634f49fabae9213759f00
- rules/sources/sec.submissions.company/source.yaml:661 | AL:
- rules/sources/sec.submissions.company/source.yaml:1585 | XX:
- .planning/workstreams/sec-configured-fields/TICKET.md:9 | 6,414 Company / 3,052 CIK+LEI
- .planning/workstreams/company-main-retirement/TICKET.md:9 | Resolve remaining active MDM classification
- .planning/workstreams/company-main-retirement/TICKET.md:11 | Complete census/cascade/provenance
- .planning/workstreams/company-census-evidence/TICKET.md:13 | 6,414 Company / 3,052 CIK+LEI
- .planning/workstreams/company-census-evidence/TICKET.md:14 | parent issue20 L3
- .planning/workstreams/gleif-configured-fields/TICKET.md:10 | 6,414 Company / 3,052 CIK+LEI
- .planning/workstreams/company-address/TICKET.md:12 | delete all old parsers
- .planning/workstreams/gleif-configured-reading/TICKET.md:9 | #841
- .planning/workstreams/gleif-configured-reading/TICKET.md:10 | generic XML record framing
- .planning/workstreams/gleif-configured-reading/TICKET.md:13 | 6,414 Company / 3,052 CIK+LEI
- .planning/workstreams/gleif-member-contracts/TICKET.md:10 | 6,414 Company / 3,052 CIK+LEI
- .planning/workstreams/gleif-member-contracts/TICKET.md:56 | company-census-evidence/TICKET.md:18
- .planning/workstreams/gleif-member-contracts/TICKET.md:66 | session 30251
- .planning/workstreams/company-configured-preparation/TICKET.md:10 | b0b406468079a62dfc1aad53245f8d31d203acb4
- .planning/workstreams/company-configured-preparation/TICKET.md:17 | b0b406468079a62dfc1aad53245f8d31d203acb4
- .planning/workstreams/company-configured-preparation/TICKET.md:26 | 3da078f81c2a4a3eec43e2f738c28cee5d8b7bf8
