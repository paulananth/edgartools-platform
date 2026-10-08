# How much of the goal Claude and Codex have completed

Read 2026-10-08 06:46 EDT on `origin/main` `862a1e66262026419cb42ebca36a2bb4e07e417d` (PR #865). This file is the measurement. It changes no ticket, rule, or source file.

The primary checkout `/Users/aneenaananth/projects/edgartools-platform` is still `main` at `a60ba016`, behind `origin/main`, and was not fast-forwarded. Its short status is still only `.planning/workstreams/fix-pipelines/STATE.md` (modified) and `infra/aws-prod-application.json.bak-20260915-predeploy` (untracked).

## The two goals

These are different ends. A checkbox count on one does not finish the other.

- **Profiling program (Claude).** `.scratch/profiling/map.md:5` says the program ends when the operator accepts the recreation proof's `DIFF.md`. `.scratch/profiling/map.md:10` still says phase B starts after Codex's old-parser retirement goal is merged.
- **Old-parser retirement (Codex).** The tickets that carry the goal still leave the same gate open: an installed empty-store population of 6,414 Companies and 3,052 CIK+LEI bindings, unchanged replay and recovery, then removal of the old parsers and parent L3–L8. See `.planning/workstreams/sec-configured-fields/TICKET.md:9` and `.planning/workstreams/company-main-retirement/TICKET.md:11`.

Handoff #860 (`e21c9de1`) is the seam list between those goals. It is not either goal.

## Handoff #860

Claude's three actions are on `origin/main`. Codex's three actions are not. They are in open PR #866 (`codex/handoff-x123-j1-20261008`), whose body says the pull request does not complete parser retirement and that X1 waits for the operator's merge word. At 06:46 EDT the five CI jobs on that pull request were still pending.

| Item | Owner | On `origin/main` |
|---|---|---|
| C1 | Claude | Done. `.scratch/profiling/issues/02-rdm-database.md:19` stays struck and names merge `716cb999418d47f82acc2412021f62d4c724d8ce`. PR #862, `4840c6ba`. |
| C2 | Claude | Done. `.scratch/profiling/issues/08-recreation-proof.md:22` names `.scratch/profiling/trials/proof/rulings.jsonl`, 358 rulings, each marked replayed and valid only in the sandbox, stamped 2026-10-07 21:33 ET. PR #863, `4a673ec6`. |
| C3 | Claude | Done. `.scratch/profiling/issues/02-rdm-database.md:35` is checked. `edgar_warehouse/mdm/clean/quality.py:121` reads the published pin. `edgar_warehouse/mdm/clean/quality.py:128` loads `files.reference_pin`. `rules/sources/sec.submissions.company/quality.yaml:75` is `36270dc9e924128f1338ecee2fd4684f2c13b35303e634f49fabae9213759f00`. `rules/reference/sec-place-codes.yaml` is gone. `rules/reference/published/sec-place-codes/1/canonical.jsonl` remains. PR #862. |
| J1 | Operator, then both | Claude's half is on main. `.scratch/profiling/issues/07b-name-based-matching.md:34` quotes the operator, 2026-10-08 06:19 ET: "Proven name rules may bind (Recommended)". `name_census_match@1` may bind when the name is unique on both sides and a second fact agrees. `name_id@1` stays lookup only. No function changed. PR #865, `862a1e66`. Codex's copy of those words is in PR #866, on `.scratch/company-mastering/issues/08-qualify-sec-to-gleif-fuzzy-binding.md`. That sentence is absent from the file on `origin/main`. |
| X1 | Codex | Not on main. `.scratch/profiling/issues/02-rdm-database.md:32` is still the open handoff. `rules/sources/sec.submissions.company/source.yaml:656` is still `AL:` and `rules/sources/sec.submissions.company/source.yaml:1580` is still `XX:`. `36270dc9` is absent from that file. PR #866 adds the pin beside the rows. |
| X2 | Codex | Not on main. `.planning/workstreams/gleif-member-contracts/TICKET.md:56` still says OSError 28 and that no successful runtime report exists. `.planning/workstreams/gleif-member-contracts/TICKET.md:66` still says scan session 30251 has no completed report. PR #866 checks those lines against the six completed reports. |
| X3 | Codex | Not on main. `.planning/workstreams/company-configured-preparation/TICKET.md:10` and `.planning/workstreams/company-configured-preparation/TICKET.md:26` are still unchecked. `.planning/workstreams/company-configured-preparation/TICKET.md:17` still says CI `37609354821` is running. `.planning/workstreams/gleif-configured-reading/TICKET.md:9` and `.planning/workstreams/gleif-configured-reading/TICKET.md:10` are still unchecked. PR #866 records the merges. |

Claude has finished every action #860 assigned to Claude, including recording J1. Codex has the matching edits in one open pull request and none of them are merged.

## Profiling program

`.scratch/profiling/map.md` has 16 ticket rows.

Done on the map: 00 (`.scratch/profiling/map.md:18`), 01 (`.scratch/profiling/map.md:19`), 01a (`.scratch/profiling/map.md:20`), 01b (`.scratch/profiling/map.md:21`), 01c (`.scratch/profiling/map.md:22`), 03 (`.scratch/profiling/map.md:24`), 04 (`.scratch/profiling/map.md:25`), 04b (`.scratch/profiling/map.md:26`), 04c (`.scratch/profiling/map.md:27`), and 07b (`.scratch/profiling/map.md:31`). That is 10 of 16. Those are the phase A rows, plus 07b.

Partial:

- Ticket 02 (`.scratch/profiling/map.md:23`). The pin, the counts run, `in_reference@1`, and the YAML removal are done. The one real open line is the contract pin, which is Codex X1.
- Ticket 05 (`.scratch/profiling/map.md:28`). MDM and RDM are done. `.scratch/profiling/issues/05-agent-context-views-and-command.md:27` (`silver.table_context`) stays open because ticket 06 has not started. `.scratch/profiling/issues/05-agent-context-views-and-command.md:30` (`mdm migrate` for 005, 006, and 007) is also still open.
- Ticket 08 (`.scratch/profiling/map.md:33`). Cohort (#859), slice, rulings file, sandbox, and the C2 replay are checked (`.scratch/profiling/issues/08-recreation-proof.md:15` through `.scratch/profiling/issues/08-recreation-proof.md:22`, with the baseline and the cold agent struck as waiting on Codex). Still open: the cold agent's use of the rulings (line 23), sandbox mastering (line 24), the configured GLEIF read for the baseline (line 25), `.scratch/profiling/issues/08-recreation-proof.md:26` (`DIFF.md`), review and merge (line 29), and `.scratch/profiling/issues/08-recreation-proof.md:30` (operator acceptance). No `DIFF.md` exists under `.scratch/profiling/`.

Not started: ticket 06 (`.scratch/profiling/map.md:29`), ticket 07 (`.scratch/profiling/map.md:30`), and ticket 07c (`.scratch/profiling/map.md:32`). Each checklist is still all unchecked, and 06 and 07 are blocked by the retirement gate on `.scratch/profiling/map.md:10`.

The profiling destination is not met. Phase A is done. Phase B has the RDM work and the start of the proof. The proof's baseline and cold agent are explicitly waiting on Codex's retirement of Company preparation.

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
- #844 (`b0b40646`) bundled Company preparation. The population lines on that ticket stay open.
- #854 (`f56f8548`) qualified pinned census evidence. Census lines 13 and 14 stay open.
- #857 (`220b8a49`) replaced GLEIF field extraction. `.planning/workstreams/gleif-configured-fields/TICKET.md:10` stays open.
- #858 (`f9c0561f`) replaced SEC Company and Person field extraction. `.planning/workstreams/sec-configured-fields/TICKET.md:9` stays open.
- #864 (`0b2f7c12`) retired the handwritten Company address derivation. `.planning/workstreams/company-address/TICKET.md:12` stays open.

PR #866 does not claim this gate. Its body says the handoff does not complete parser retirement.

## Where that leaves the work

Claude has completed the phase A profiling tickets and every Claude action in handover #860. The profiling program itself is short of its end: `DIFF.md` is not written and the operator has not accepted it. Tickets 06, 07, and 07c have not started.

Codex has merged the configured-reading building blocks above and one address-derivation retirement. The retirement goal those tickets name is not complete. The #860 items assigned to Codex are implemented on open PR #866 and are not on `origin/main`.

## Citation index

Each row is `path:line | substring of that line` on `862a1e66`, except the two absence checks noted in the prose.

- .scratch/profiling/map.md:5 | DIFF.md is accepted by the operator
- .scratch/profiling/map.md:10 | phase B starts after Codex's old-parser retirement goal is merged
- .scratch/profiling/map.md:18 | done (#823)
- .scratch/profiling/map.md:23 | contract-embedded rows gain the pin: Codex (X1)
- .scratch/profiling/map.md:28 | silver waits for 06
- .scratch/profiling/map.md:29 | open
- .scratch/profiling/map.md:30 | open
- .scratch/profiling/map.md:31 | done (#838)
- .scratch/profiling/map.md:32 | open
- .scratch/profiling/map.md:33 | baseline and cold agent wait for Codex's retirement
- .scratch/profiling/issues/02-rdm-database.md:19 | 716cb999418d47f82acc2412021f62d4c724d8ce
- .scratch/profiling/issues/02-rdm-database.md:32 | Contract-embedded tables gain the pin
- .scratch/profiling/issues/02-rdm-database.md:35 | YAML removed
- .scratch/profiling/issues/07b-name-based-matching.md:34 | Proven name rules may bind
- .scratch/profiling/issues/08-recreation-proof.md:22 | rulings.jsonl
- .scratch/profiling/issues/08-recreation-proof.md:26 | DIFF.md: every line matched or explained
- .scratch/profiling/issues/08-recreation-proof.md:30 | Operator accepts
- .scratch/profiling/issues/05-agent-context-views-and-command.md:27 | silver.table_context
- .scratch/profiling/issues/05-agent-context-views-and-command.md:30 | mdm migrate
- edgar_warehouse/mdm/clean/quality.py:121 | def _reference_keys
- edgar_warehouse/mdm/clean/quality.py:128 | files.reference_pin
- rules/sources/sec.submissions.company/quality.yaml:75 | 36270dc9e924128f1338ecee2fd4684f2c13b35303e634f49fabae9213759f00
- rules/sources/sec.submissions.company/source.yaml:656 | AL:
- rules/sources/sec.submissions.company/source.yaml:1580 | XX:
- .planning/workstreams/sec-configured-fields/TICKET.md:9 | 6,414 Company / 3,052 CIK+LEI
- .planning/workstreams/company-main-retirement/TICKET.md:9 | Resolve remaining active MDM classification
- .planning/workstreams/company-main-retirement/TICKET.md:11 | Complete census/cascade/provenance
- .planning/workstreams/company-census-evidence/TICKET.md:13 | 6,414 Company / 3,052 CIK+LEI
- .planning/workstreams/company-census-evidence/TICKET.md:14 | parent issue20 L3
- .planning/workstreams/gleif-configured-fields/TICKET.md:10 | 6,414 Company / 3,052 CIK+LEI
- .planning/workstreams/company-address/TICKET.md:12 | delete all old parsers
- .planning/workstreams/gleif-configured-reading/TICKET.md:9 | Add configured GLEIF member contracts
- .planning/workstreams/gleif-configured-reading/TICKET.md:10 | generic XML record framing
- .planning/workstreams/gleif-configured-reading/TICKET.md:13 | 6,414 Company / 3,052 CIK+LEI
- .planning/workstreams/gleif-member-contracts/TICKET.md:10 | 6,414 Company / 3,052 CIK+LEI
- .planning/workstreams/gleif-member-contracts/TICKET.md:56 | OSError 28
- .planning/workstreams/gleif-member-contracts/TICKET.md:66 | session 30251
- .planning/workstreams/company-configured-preparation/TICKET.md:10 | separate reviewable PR
- .planning/workstreams/company-configured-preparation/TICKET.md:17 | 37609354821 running
- .planning/workstreams/company-configured-preparation/TICKET.md:26 | publish a separate PR
