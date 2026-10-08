# Handover to Claude and Codex

Read 2026-10-07 20:52 EDT, on `origin/main` `f9c0561f16b117c033cfb8eb4614e9699d4a15b9` ("Replace SEC Company and Person field extraction with configured reading", PR #858, merged 2026-10-08T00:27:06Z).

This file is the handover. It does not implement the actions below.

## Checkout this list was read from

- `origin/main` is `f9c0561f16b117c033cfb8eb4614e9699d4a15b9`. `gh pr list --state open` was empty.
- The primary checkout `/Users/aneenaananth/projects/edgartools-platform` is still `main` at `a60ba01622a61314654a89e5ef1f588b9a0639a5` (PR #859). It was not fast-forwarded. Leave it. Its short status is only:

  ```text
   M .planning/workstreams/fix-pipelines/STATE.md
  ?? infra/aws-prod-application.json.bak-20260915-predeploy
  ```

- The status captured before this review was `ba2b9cc76294656f64b98039f4754dbd38fcf10d` (PR #853). Local `main` then moved to `a60ba016`. `origin/main` then moved once more, to `f9c0561f`.
- `rules/sources/sec.submissions.company/source.yaml` line numbers below are from `f9c0561f`. On that commit the file is 1,582 lines. `36270dc9` is absent from it.
- These files are the same blob on `a60ba016` and `f9c0561f`: `rules/sources/sec.submissions.company/quality.yaml`, `crates/source-contract/src/reference.rs`, `edgar_warehouse/mdm/clean/quality.py`, `edgar_warehouse/rules/files.py`, `docs/specs/rdm/spec.md`, `rules/merge/kinds/company.yaml`, `rules/merge/reference-pins.yaml`, the `.scratch/profiling/` tickets cited below, and the configured-reading tickets cited below except `.planning/workstreams/sec-configured-fields/TICKET.md`. The `a60ba016..f9c0561f` diff is the #858 field-extraction change (14 files) and does not touch those others.
- Do not recreate `/Users/aneenaananth/projects/edgartools-platform-claude-profiling-05-rdm`. It is missing. PR #847 is already merged. Leave `/Users/aneenaananth/projects/edgartools-platform-claude-profiling-08-proof` (`claude/profiling-08-proof`) alone.

## Who takes what

Claude takes C1, C2, and C3. Codex takes X1, X2, and X3. Both wait on J1. The operator decides J1. No runtime edits a rule for J1.

Each runtime starts a new branch from `origin/main` `f9c0561f`, in its own worktree (`claude/…` or `codex/…`). Do not commit on the dirty primary `main`. Do not fast-forward it. Run `bash scripts/dev/overlap_guard.sh` before every commit and push. Stop if it exits 1.

## Not an action

### Seam (a) — phase B gate versus open retirement

Not an action. Two artifacts:

- `.scratch/profiling/map.md:10` says phase B starts after Codex's old-parser retirement goal is merged. `.scratch/profiling/map.md:29` and `.scratch/profiling/map.md:30` leave tickets 06 and 07 open, blocked by that gate. `.scratch/profiling/map.md:33` leaves ticket 08 open.
- `.planning/workstreams/company-main-retirement/TICKET.md:9` and `.planning/workstreams/company-main-retirement/TICKET.md:11` are unchecked. `.planning/workstreams/company-census-evidence/TICKET.md:13` and `.planning/workstreams/company-census-evidence/TICKET.md:14` are unchecked. `.planning/workstreams/gleif-configured-fields/TICKET.md:10` is unchecked. `.planning/workstreams/sec-configured-fields/TICKET.md:9` still requires Company preparation, census, provenance, GLEIF consumers, the installed 6,414 / 3,052 population, and parent L3–L8.

`.scratch/profiling/issues/02-rdm-database.md:7` records the operator ruling at 2026-10-07 06:39 ET that started ticket 02 before that retirement merged. That ruling is not itself an action.

Do not start tickets 06 or 07. Do not check `company-main-retirement` lines 9 or 11. Do not mark old-parser retirement done. #854, #857, and merged #858 (`f9c0561f`) do not close the 6,414 / 3,052 population.

### Seam (d) — merged boxes that are already closed

Not an action. Two artifacts:

- `.scratch/profiling/issues/02-rdm-database.md:39` is checked. PR #848 is merged as `ba692ec601c0bb7575efeb5503beb3971f316b56`.
- `.scratch/profiling/issues/05-agent-context-views-and-command.md:24` is checked. PR #847 is merged as `626cf06c60ddd84774a03378447ea2d955a0bfc6`.

`.scratch/profiling/issues/05-agent-context-views-and-command.md:27` (`silver.table_context`) stays open because seam (a) blocks ticket 06. The remaining stale-merge action is C1.

### Seams that already hold

Leave these as they are. Do not open work for them, and do not ask for a merge word on #859.

- `.scratch/profiling/issues/04b-parent-relationship-types.md:128` ("Silence ends nothing") and `.scratch/profiling/issues/04b-parent-relationship-types.md:129` ("Every parent type") are checked, no change, 2026-10-07 18:02 ET. `.scratch/profiling/map.md:26` records #850 and #851.
- `.scratch/profiling/issues/02-rdm-database.md:34` is checked: 6,414 Companies, 3,716 GLEIF records; bindings 6,414 / 2,861 / 191; open reviews 664 / 312; 16 minutes; 2026-10-07 18:31 ET.
- `.scratch/profiling/issues/08-recreation-proof.md:15` is checked. The cohort is in the repo via #859 (`a60ba016`).
- `.scratch/profiling/issues/05-agent-context-views-and-command.md:21` is checked.

## Claude

Work from a new `claude/` branch and worktree at `origin/main` `f9c0561f`.

### C1 — Ticket 02 still says PR #834 is open

Owner: Claude.

Artifacts:

- `.scratch/profiling/issues/02-rdm-database.md:19` is a struck deferral that still says Codex's retirement has not merged and that PR #834 is open.
- PR #834 is merged. Merge commit `716cb999418d47f82acc2412021f62d4c724d8ce` (2026-10-07T00:26:33Z).

The disagreement: the struck line describes an open PR. The PR is merged.

Action: keep line 19 struck. Replace the words "Codex's retirement has still not merged (PR #834 open)" with the merge commit `716cb999418d47f82acc2412021f62d4c724d8ce`. Do not change any other checklist box on that file.

Done when line 19 stays struck, names `716cb999418d47f82acc2412021f62d4c724d8ce`, and no longer says PR #834 is open, and every other box on `.scratch/profiling/issues/02-rdm-database.md` has the same checked or unchecked state as `f9c0561f`.

### C2 — Ticket 08 names no rulings file

Owner: Claude.

Artifacts:

- `.scratch/profiling/issues/08-recreation-proof.md:16` says "Rulings file replayed in sandbox" and names no file. Lines 17–19 stay behind it.
- `.scratch/profiling/plan.md:129` says recorded rulings are replayed, marked "replayed", and valid only in the sandbox.

The missing handoff: the checklist line requires a rulings file and the plan requires the replay, and ticket 08 points at no path. The ruling that bounds the proof is `.scratch/profiling/issues/08-recreation-proof.md:7` through `.scratch/profiling/issues/08-recreation-proof.md:11`. `.scratch/profiling/issues/08-recreation-proof.md:9` quotes the operator, "Local feeds only": only SEC submissions, the GLEIF Golden Copy, and the 999 13F tables on hand; no production read.

Action: name the rulings path on line 16, then replay those recorded rulings in the sandbox and stamp the line in ET. Do not write a second cohort. Line 15 already holds the cohort. Do not start lines 17–19 before line 16 is done. `.scratch/profiling/map.md:33` stays open until the proof ends.

Done when line 16 names one repo path, the sandbox replay is marked replayed and valid only in the sandbox, the line is stamped in ET, line 15 is unchanged, and lines 17–19 are still unchecked.

### C3 — `in_reference@1` still hashes the YAML

Owner: Claude. `rules/sources/sec.submissions.company/quality.yaml` is Codex's path (`rules/sources/**`). Run `bash scripts/dev/overlap_guard.sh` before the commit that touches it. If the guard exits 1, stop and ask the operator. Do not edit `rules/sources/sec.submissions.company/source.yaml` in this change. That file is X1, on a separate Codex branch from `f9c0561f`.

Artifacts:

- `.scratch/profiling/issues/02-rdm-database.md:33` defers `in_reference@1` because the check still reads the YAML. `.scratch/profiling/issues/02-rdm-database.md:35` says the YAML comes out only after `in_reference@1` reads the pin. `docs/specs/rdm/spec.md:161` and `docs/specs/rdm/spec.md:162` say the same: the check reads the pinned version, and the YAML is removed only after the same mastering counts.
- `edgar_warehouse/mdm/clean/quality.py:122` defines `_reference_keys`. `edgar_warehouse/mdm/clean/quality.py:128` opens `rules/reference/<table>.yaml`. `edgar_warehouse/mdm/clean/quality.py:129` compares sha256 of those bytes. `edgar_warehouse/mdm/clean/quality.py:130` raises `QualityError` when they differ. `rules/sources/sec.submissions.company/quality.yaml:70` is `in_reference@1`. `rules/sources/sec.submissions.company/quality.yaml:75` still pins `5a5a504286180523272d74fbbdc35078bb636bd4343309637041970c3e803a12`, which is the sha256 of `rules/reference/sec-place-codes.yaml` (19,259 bytes).

The published pin is a different file. `rules/merge/reference-pins.yaml:7` through `rules/merge/reference-pins.yaml:10` pin `sec-place-codes` version 1 at `36270dc9e924128f1338ecee2fd4684f2c13b35303e634f49fabae9213759f00`. That digest is `rules/reference/published/sec-place-codes/1/canonical.jsonl` (90,296 bytes). `edgar_warehouse/rules/files.py:349` builds that `canonical.jsonl` path. `edgar_warehouse/rules/files.py:351` compares the digest. `edgar_warehouse/rules/files.py:352` raises `RulesFileError` on a mismatch.

Writing `36270dc9…` into `quality.yaml:75` while `_reference_keys` still hashes the YAML fails closed: the YAML digest stays `5a5a5042…`. Deleting `rules/reference/sec-place-codes.yaml` while the checker still opens it breaks `in_reference@1`. The YAML stays until `_reference_keys` reads the published pin.

Action, one change: make `_reference_keys` read the published `canonical.jsonl` through the path `files.py:349` already builds, and compare that digest. In that same change, set the `quality.yaml:75` argument to `36270dc9e924128f1338ecee2fd4684f2c13b35303e634f49fabae9213759f00`, remove `rules/reference/sec-place-codes.yaml`, and check `.scratch/profiling/issues/02-rdm-database.md:35` with an ET stamp. `.scratch/profiling/map.md:23` already says removing the YAML waits for this handoff.

Done when `_reference_keys` hashes `canonical.jsonl`, `quality.yaml:75` is `36270dc9e924128f1338ecee2fd4684f2c13b35303e634f49fabae9213759f00`, the YAML file is gone, ticket 02 line 35 is checked and stamped in ET, `source.yaml` is untouched, and the overlap guard passed on the commit that edited `quality.yaml`.

## Codex

Work from a new `codex/` branch and worktree at `origin/main` `f9c0561f`. #858 is merged. Do not add the pin on that branch. Do not mark old-parser retirement done.

### X1 — Place rows stay; the pin is added beside them

Owner: Codex.

Artifacts:

- `docs/specs/rdm/spec.md:121` says source contracts keep embedding reference rows. `docs/specs/rdm/spec.md:123` says the contract embeds the rows and `{code_set, version, sha256}`. `docs/specs/rdm/spec.md:124` says the reader does not change. `docs/specs/rdm/spec.md:164` names this as the handoff to Codex. `.scratch/profiling/issues/02-rdm-database.md:32` is the unchecked handoff line.
- `rules/sources/sec.submissions.company/source.yaml:615` is `reference: places` and `rules/sources/sec.submissions.company/source.yaml:616` is `column: country`. `rules/sources/sec.submissions.company/source.yaml:629` is `reference: places` and `rules/sources/sec.submissions.company/source.yaml:630` is `column: subdivision`. `rules/sources/sec.submissions.company/source.yaml:654` opens `references:` and `rules/sources/sec.submissions.company/source.yaml:655` opens `places:`. Rows run from `rules/sources/sec.submissions.company/source.yaml:656` (`AL:`) through `rules/sources/sec.submissions.company/source.yaml:1580` (`XX:`), `rules/sources/sec.submissions.company/source.yaml:1581` (`country: null`), and `rules/sources/sec.submissions.company/source.yaml:1582` (`subdivision: false`).

The missing handoff: ticket 02 published the pin and asked Codex to put it on the contract. The contract still has only the inline rows.

`crates/source-contract/src/reference.rs:17` rejects a reference table that is not a map of at most 10,000 keyed rows. `crates/source-contract/src/reference.rs:21` rejects a row that is not a map of 1..32 columns. `crates/source-contract/src/reference.rs:87` reads `read["references"][reference].get(&key)`. A pin object in place of the row map, or as a key inside `places`, is rejected. The lookup does not change.

Action: keep every inline `places` row from `AL` through `XX`. Add this object beside those rows, as a sibling of `references` under `read`, so `validate` still sees only keyed rows and the lookup still uses `references.places`:

```yaml
code_set: sec-place-codes
version: "1"
sha256: 36270dc9e924128f1338ecee2fd4684f2c13b35303e634f49fabae9213759f00
```

Leave the country lookup (`source.yaml:615`–`616`) and the subdivision lookup (`source.yaml:629`–`630`) unchanged. Leave `reference.rs:87` unchanged. Do not set `quality.yaml:75` to `36270dc9…`. Do not delete `rules/reference/sec-place-codes.yaml`. Those two stays are C3. Update digest pins that hash this contract, because the contract bytes change. Do not change lookup behavior.

Done when this change is on `origin/main` (merge waits for the operator's word), `AL` through `XX` are still inline rows, the `36270dc9…` pin sits beside that row map, the two lookups are unchanged, `reference.rs:87` is unchanged, `quality.yaml:75` is still `5a5a504286180523272d74fbbdc35078bb636bd4343309637041970c3e803a12`, and `rules/reference/sec-place-codes.yaml` is still present.

### X2 — Member-contract lines still say the GLEIF reports never finished

Owner: Codex. Text only.

Artifacts:

- `.planning/workstreams/company-census-evidence/TICKET.md:18` is checked: six completed GLEIF runtime corpus reports, Level 1 3,428,477, relationships 487,721, reporting exceptions 6,351,397, in each format (2026-10-07 17:55 ET).
- `.planning/workstreams/gleif-member-contracts/TICKET.md:56` still says the Level 1 JSON runtime failed with OSError 28 and that no successful runtime report exists. `.planning/workstreams/gleif-member-contracts/TICKET.md:66` still says scan session 30251 has no completed report and that Level 1 JSON is past 1.6 million records.

The disagreement: census line 18 records the six completed reports. Lines 56 and 66 still say those reports do not exist.

Action: check only lines 56 and 66, by citing census line 18. Do not retry the OSError 28 run. Leave `.planning/workstreams/gleif-member-contracts/TICKET.md:8`, `:9`, `:10`, `:11`, `:12`, `:57`, `:61`, and `:67` unchecked. Leave census lines 13 and 14 unchecked. Leave `.planning/workstreams/gleif-configured-fields/TICKET.md:10` unchecked.

Done when lines 56 and 66 are checked, each cites census line 18 and the six counts, and the lines listed above are still unchecked.

### X3 — Checklist lines still describe merged PRs as open work

Owner: Codex. Text only. #858 did not touch these three files. Its ticket edit is `.planning/workstreams/sec-configured-fields/TICKET.md` only. Do not edit that file here. Check a line only when the cited merge covers every clause of that line's sentence. Leave the box unchecked when it does not.

**GLEIF configured reading.** `.planning/workstreams/gleif-configured-reading/TICKET.md:9` and `.planning/workstreams/gleif-configured-reading/TICKET.md:10` are unchecked. Cite merged #841 `e6b541b373d114a6a10a3bc8dd84151cf26c0d38`, #834 `716cb999418d47f82acc2412021f62d4c724d8ce`, and #843 `f8f7876ee8c5e39baae74313d8a9182ecc42cb49` beside them. Check line 9 or line 10 only when those commits cover the whole sentence (member contracts, approved scope, source metadata, installed publication and refusal/recovery on line 9; generic XML framing, namespace/header/metadata assertions, and all three members on line 10). Leave `.planning/workstreams/gleif-configured-reading/TICKET.md:11` through `.planning/workstreams/gleif-configured-reading/TICKET.md:15` unchecked.

**GLEIF member contracts.** The header `.planning/workstreams/gleif-member-contracts/TICKET.md:3` already says PRs #833, #834, and #841 are merged. `.planning/workstreams/gleif-member-contracts/TICKET.md:5` stays unchecked beside `.planning/workstreams/gleif-member-contracts/TICKET.md:13`, which checks #841 at `e6b541b373d114a6a10a3bc8dd84151cf26c0d38`. Cite #841 and #843 and keep line 5 unchecked unless both commits cover the whole sentence: JSON and XML, approved scope, and authenticated publication metadata. `.planning/workstreams/gleif-member-contracts/TICKET.md:18` stays unchecked beside `.planning/workstreams/gleif-member-contracts/TICKET.md:21`, which checks typed `equal`. Do not check lines 8–12, 57, 61, or 67. X2 owns lines 56 and 66.

**Company configured preparation.** `.planning/workstreams/company-configured-preparation/TICKET.md:10` is unchecked ("separate reviewable PR") while `.planning/workstreams/company-configured-preparation/TICKET.md:21` records #844 merged at `b0b40646`. The full merge is `b0b406468079a62dfc1aad53245f8d31d203acb4`. `.planning/workstreams/company-configured-preparation/TICKET.md:17` is checked and still says full CI `37609354821` is running. Replace that running-CI clause with merge `b0b406468079a62dfc1aad53245f8d31d203acb4`, and check line 10 with that same merge. `.planning/workstreams/company-configured-preparation/TICKET.md:26` is unchecked ("publish a separate PR") while #846 is merged as `3da078f81c2a4a3eec43e2f738c28cee5d8b7bf8` and lines `.planning/workstreams/company-configured-preparation/TICKET.md:24` and `.planning/workstreams/company-configured-preparation/TICKET.md:27` are checked. Check line 26 citing #846. `.planning/workstreams/company-configured-preparation/TICKET.md:25` stays open: it wires receipt-bound census evidence into preparation. #854 qualified reuse of the pinned 43,245 census entries (census line 11) and did not replace active consumers (census line 13). Leave lines 7, 8, 9, and 11 unchecked.

Done when the three files above cite those merge commits, a box is checked only where the citation covers the whole sentence, line 17 no longer says CI `37609354821` is running, and the lines this item says to leave open are still unchecked.

## Joint

### J1 — Who may bind a CIK to an LEI

Owner: the operator. Claude and Codex both wait. No code edit, and no rule edit, until the operator's words are on both artifacts below.

Artifacts:

- `.scratch/profiling/issues/07b-name-based-matching.md:30` says `name_id` is lookup only and is used only where no identifier exists. `.scratch/profiling/issues/07b-name-based-matching.md:29` is the recipe: NFKC, case fold, every token kept, sha256. `.scratch/profiling/issues/07b-name-based-matching.md:31` is struck: the live sources carry CIK or LEI, so none takes `name_id`. The recipe itself is `skills/data-profiling/scripts/profiling/name_matching.py:272` (`name_id`), using `skills/data-profiling/scripts/profiling/name_matching.py:48` and `skills/data-profiling/scripts/profiling/name_matching.py:49` (`tokens`, via `name_norm`) and `skills/data-profiling/scripts/profiling/names.py:24`. `edgar_warehouse/mdm/clean/adapters.py:55` defines `_name_id`. `edgar_warehouse/mdm/clean/adapters.py:76` registers `name_id@1`. Do not cite `skills/data-profiling/SKILL.md` as the recipe.
- `rules/merge/kinds/company.yaml:236` is rule `sec-gleif-name-jurisdiction`. `rules/merge/kinds/company.yaml:242` emits and `rules/merge/kinds/company.yaml:243` is `bind`, from `rules/merge/kinds/company.yaml:246` `name_census_match@1`. `rules/merge/kinds/company.yaml:266` is rule `sec-gleif-name-postal`. `rules/merge/kinds/company.yaml:265` is the previous rule's `gleif_field: jurisdiction`. `rules/merge/kinds/company.yaml:272` emits and `rules/merge/kinds/company.yaml:273` is `bind`, from `rules/merge/kinds/company.yaml:276` `name_census_match@1`.

The disagreement: profiling `name_id` is a lookup, and only where no id exists. The Company rules emit `bind` from a name-census match, which binds a CIK to an LEI. `rules/merge/policy.yaml:67` records an older operator "yes" that switched `sec-gleif-name-jurisdiction` on (2026-09-30T01:04:15Z). That sentence is not this decision.

Decision requested: which function may bind a CIK to an LEI. Claude writes the operator's words onto `07b-name-based-matching.md`. Codex writes the same words onto the Company merge-rule ticket that owns `rules/merge/kinds/company.yaml` (or onto that file's ruling note if no ticket is open). Neither runtime edits `name_id@1` or `name_census_match@1` before those words are on both.

Done when both artifacts quote the operator's words and those words name which function may bind a CIK to an LEI.

## Citation index

Each row is `path:line | substring of that line` on `f9c0561f`.

- .scratch/profiling/map.md:10 | phase B starts after Codex's old-parser retirement goal is merged
- .scratch/profiling/map.md:23 | removing the YAML waits for the Codex handoff
- .scratch/profiling/map.md:26 | done: #850, #851
- .scratch/profiling/map.md:29 | Codex retirement merged
- .scratch/profiling/map.md:30 | Codex retirement merged
- .scratch/profiling/map.md:33 | 08-recreation-proof.md
- .scratch/profiling/issues/02-rdm-database.md:7 | starting this phase B ticket before Codex's old-parser retirement merged
- .scratch/profiling/issues/02-rdm-database.md:19 | PR #834 open
- .scratch/profiling/issues/02-rdm-database.md:32 | Contract-embedded tables gain the pin
- .scratch/profiling/issues/02-rdm-database.md:33 | still reads the YAML
- .scratch/profiling/issues/02-rdm-database.md:34 | 6,414 Companies, 3,716 GLEIF
- .scratch/profiling/issues/02-rdm-database.md:35 | YAML removed
- .scratch/profiling/issues/02-rdm-database.md:39 | ba692ec6
- .scratch/profiling/issues/08-recreation-proof.md:7 | Only SEC submissions
- .scratch/profiling/issues/08-recreation-proof.md:9 | Local feeds only
- .scratch/profiling/issues/08-recreation-proof.md:15 | Cohort list
- .scratch/profiling/issues/08-recreation-proof.md:16 | Rulings file replayed in sandbox
- .scratch/profiling/plan.md:129 | Recorded rulings are replayed
- .scratch/profiling/issues/05-agent-context-views-and-command.md:21 | Pointers in data-onboarding
- .scratch/profiling/issues/05-agent-context-views-and-command.md:24 | 626cf06c
- .scratch/profiling/issues/05-agent-context-views-and-command.md:27 | silver.table_context
- .scratch/profiling/issues/07b-name-based-matching.md:29 | every token kept, sha256
- .scratch/profiling/issues/07b-name-based-matching.md:30 | lookup only
- .scratch/profiling/issues/07b-name-based-matching.md:31 | none takes a name id
- .scratch/profiling/issues/04b-parent-relationship-types.md:128 | Silence ends nothing
- .scratch/profiling/issues/04b-parent-relationship-types.md:129 | Every parent type
- .planning/workstreams/company-main-retirement/TICKET.md:9 | Resolve remaining active MDM classification
- .planning/workstreams/company-main-retirement/TICKET.md:11 | Complete census/cascade/provenance
- .planning/workstreams/company-census-evidence/TICKET.md:13 | 6,414 Company / 3,052 CIK+LEI
- .planning/workstreams/company-census-evidence/TICKET.md:14 | Complete whole-source configured census construction
- .planning/workstreams/company-census-evidence/TICKET.md:18 | six completed GLEIF runtime corpus reports
- .planning/workstreams/gleif-configured-fields/TICKET.md:10 | 6,414 Company / 3,052 CIK+LEI
- .planning/workstreams/gleif-member-contracts/TICKET.md:3 | PRs #833, #834 and #841 are merged
- .planning/workstreams/gleif-member-contracts/TICKET.md:5 | both JSON and XML
- .planning/workstreams/gleif-member-contracts/TICKET.md:13 | e6b541b373d114a6a10a3bc8dd84151cf26c0d38
- .planning/workstreams/gleif-member-contracts/TICKET.md:18 | malformed creator contract cannot pin inconsistent counts
- .planning/workstreams/gleif-member-contracts/TICKET.md:21 | Implement generic typed
- .planning/workstreams/gleif-member-contracts/TICKET.md:56 | OSError 28
- .planning/workstreams/gleif-member-contracts/TICKET.md:66 | session 30251
- .planning/workstreams/gleif-configured-reading/TICKET.md:9 | Add configured GLEIF member contracts
- .planning/workstreams/gleif-configured-reading/TICKET.md:10 | generic XML record framing
- .planning/workstreams/gleif-configured-reading/TICKET.md:11 | Replace active GLEIF runtime consumers
- .planning/workstreams/gleif-configured-reading/TICKET.md:15 | Independent review, affected tests
- .planning/workstreams/company-configured-preparation/TICKET.md:10 | separate reviewable PR
- .planning/workstreams/company-configured-preparation/TICKET.md:17 | 37609354821 running
- .planning/workstreams/company-configured-preparation/TICKET.md:21 | b0b40646
- .planning/workstreams/company-configured-preparation/TICKET.md:24 | captured-name-key-parity.json
- .planning/workstreams/company-configured-preparation/TICKET.md:25 | Wire receipt-bound census evidence
- .planning/workstreams/company-configured-preparation/TICKET.md:26 | publish a separate PR
- .planning/workstreams/company-configured-preparation/TICKET.md:27 | installed-name-key-proof.json
- .planning/workstreams/sec-configured-fields/TICKET.md:9 | 6,414 Company / 3,052 CIK+LEI
- rules/sources/sec.submissions.company/source.yaml:615 | reference: places
- rules/sources/sec.submissions.company/source.yaml:616 | column: country
- rules/sources/sec.submissions.company/source.yaml:629 | reference: places
- rules/sources/sec.submissions.company/source.yaml:630 | column: subdivision
- rules/sources/sec.submissions.company/source.yaml:654 | references:
- rules/sources/sec.submissions.company/source.yaml:655 | places:
- rules/sources/sec.submissions.company/source.yaml:656 | AL:
- rules/sources/sec.submissions.company/source.yaml:1580 | XX:
- rules/sources/sec.submissions.company/source.yaml:1581 | country: null
- rules/sources/sec.submissions.company/source.yaml:1582 | subdivision: false
- rules/sources/sec.submissions.company/quality.yaml:70 | in_reference@1
- rules/sources/sec.submissions.company/quality.yaml:75 | 5a5a504286180523272d74fbbdc35078bb636bd4343309637041970c3e803a12
- rules/merge/reference-pins.yaml:7 | sec-place-codes:
- rules/merge/reference-pins.yaml:10 | 36270dc9e924128f1338ecee2fd4684f2c13b35303e634f49fabae9213759f00
- crates/source-contract/src/reference.rs:17 | a reference table has at most 10000 keyed rows
- crates/source-contract/src/reference.rs:21 | a reference row has 1..32 columns
- crates/source-contract/src/reference.rs:87 | .get(&key)
- edgar_warehouse/mdm/clean/quality.py:122 | def _reference_keys
- edgar_warehouse/mdm/clean/quality.py:128 | f"{table}.yaml"
- edgar_warehouse/mdm/clean/quality.py:129 | hexdigest() != sha256
- edgar_warehouse/mdm/clean/quality.py:130 | differs from its pinned sha256
- edgar_warehouse/rules/files.py:349 | canonical.jsonl
- edgar_warehouse/rules/files.py:351 | pin["sha256"]
- edgar_warehouse/rules/files.py:352 | differs from its pinned sha256
- docs/specs/rdm/spec.md:121 | keep embedding reference rows
- docs/specs/rdm/spec.md:123 | contract embeds the rows
- docs/specs/rdm/spec.md:124 | The reader does not change.
- docs/specs/rdm/spec.md:161 | reads the pinned version
- docs/specs/rdm/spec.md:162 | same mastering counts
- docs/specs/rdm/spec.md:164 | handoff request to Codex
- rules/merge/kinds/company.yaml:236 | sec-gleif-name-jurisdiction
- rules/merge/kinds/company.yaml:242 | emits:
- rules/merge/kinds/company.yaml:243 | - bind
- rules/merge/kinds/company.yaml:246 | name_census_match@1
- rules/merge/kinds/company.yaml:265 | gleif_field: jurisdiction
- rules/merge/kinds/company.yaml:266 | sec-gleif-name-postal
- rules/merge/kinds/company.yaml:272 | emits:
- rules/merge/kinds/company.yaml:273 | - bind
- rules/merge/kinds/company.yaml:276 | name_census_match@1
- rules/merge/policy.yaml:67 | in their words: yes
- skills/data-profiling/scripts/profiling/name_matching.py:48 | def tokens
- skills/data-profiling/scripts/profiling/name_matching.py:49 | name_norm(value)
- skills/data-profiling/scripts/profiling/name_matching.py:272 | def name_id
- skills/data-profiling/scripts/profiling/names.py:24 | def name_norm
- edgar_warehouse/mdm/clean/adapters.py:55 | def _name_id
- edgar_warehouse/mdm/clean/adapters.py:76 | name_id@1
