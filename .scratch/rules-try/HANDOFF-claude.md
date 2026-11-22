# Handoff: finish the try-page tickets

Written 2026-11-22 11:36 ET. Read this before editing. Tickets 01, 02, and 03 are merged. Tickets 04 through 38 are open. Finish them one ticket at a time. Each ticket is its own pull request.

The spec for a ticket is its file in `.scratch/rules-try/issues/`. This handoff is how to ship that file. When the two disagree, the ticket file wins, except for the frozen shell and the shipping rules below.

## Done

| Ticket | Pull request | On main |
|---|---|---|
| 01 Open the try page | https://github.com/paulananth/edgartools-platform/pull/2020 | `7976e87e6` |
| 02 Keep a copy | https://github.com/paulananth/edgartools-platform/pull/2021 | `01ac2ef69` |
| 03 Store the try as a draft | https://github.com/paulananth/edgartools-platform/pull/2022 | `dcacb0fac` |

Start at ticket 04. Leave 01, 02, and 03 as they are.

## Next

Start ticket 04 after this handoff pull request is on main. This branch edits only this file and the map note, and a later ticket also edits the map. Then continue in number order through 38. Land a family's try file before that family's guide, because the guide records the try ticket's output. A short-word file may merge before its try file. The page ignores `<name>_full.py` until `<name>.py` exists. Ticket 38 waits until 37 has merged, because both edit the primer.

## Remaining tickets

| Ticket | Add or edit this file | What it does |
|---|---|---|
| 04 | `edgar_warehouse/rules/bench_families/read_file.py` | Paste a read document, the file bytes, and lookup lists. Call `SourceEngine.read`. Invented R1 row. No capture folder. |
| 05 | `edgar_warehouse/rules/bench_families/read_file_full.py` | Short words for that read. A bare `join` or `number` is refused. |
| 06 | `docs/rules-try/read_file.md` | Word, stored key, invented input, output from 04. No test. |
| 07 | `edgar_warehouse/rules/bench_families/group_rows.py` | Paste the plan and the input tables. Call `combine_tables`. |
| 08 | `edgar_warehouse/rules/bench_families/group_rows_full.py` | Short words for grouped rows. Refuse "how many at this path". |
| 09 | `docs/rules-try/group_rows.md` | Words, stored keys, and the R1 case. |
| 10 | `edgar_warehouse/rules/bench_families/whole_set.py` | Paste the reduce plan and the rows. Call the existing reduce finish. |
| 11 | `edgar_warehouse/rules/bench_families/whole_set_full.py` | How many rows, distinct values, most frequent. |
| 12 | `docs/rules-try/whole_set.md` | The three-row case and the tie. |
| 13 | `edgar_warehouse/rules/bench_families/check_record.py` | Paste the quality block, the fields, and the matching input. Call `quality.apply`. |
| 14 | `edgar_warehouse/rules/bench_families/check_record_full.py` | Short words for one record check. |
| 15 | `docs/rules-try/check_record.md` | The "is present" case. No in-reference check. |
| 16 | `edgar_warehouse/rules/bench_families/entity_type.py` | Paste the rule, the record, and the doc. Call `classification.classify`. |
| 17 | `edgar_warehouse/rules/bench_families/entity_type_full.py` | Short words for the entity type. |
| 18 | `docs/rules-try/entity_type.md` | The empty-ticker case. |
| 19 | `edgar_warehouse/rules/bench_families/field_value.py` | Paste the kind, subjects, claims, policy, overrides, as-of time, and policy digest. Call `select_fields`. |
| 20 | `edgar_warehouse/rules/bench_families/field_value_full.py` | Short words for choosing a field value. |
| 21 | `docs/rules-try/field_value.md` | Directory first, then the register. |
| 22 | `edgar_warehouse/rules/bench_families/attach_record.py` | Paste the policy, assertions, identities, and the bound list. Call `plan_record_matches`. |
| 23 | `edgar_warehouse/rules/bench_families/attach_record_full.py` | Short words for source record binding. Refuse a word for combining two existing masters. |
| 24 | `docs/rules-try/attach_record.md` | Both cases. The title says source record binding. |
| 25 | `edgar_warehouse/rules/bench_families/link_masters.py` | Paste claims, state, entities, as-of time, and types. Call `project`. |
| 26 | `edgar_warehouse/rules/bench_families/link_masters_full.py` | Short words for a link. A missing end stays a wait. |
| 27 | `docs/rules-try/link_masters.md` | The emitted link and the missing-start wait. |
| 28 | `edgar_warehouse/rules/bench_families/link_periods.py` | Paste sightings. Call `fold_sightings`. A missing later file does not invent an end. |
| 29 | `edgar_warehouse/rules/bench_families/link_periods_full.py` | Short words for a dated sighting and the period. |
| 30 | `docs/rules-try/link_periods.md` | The sighting-to-period case. |
| 31 | `edgar_warehouse/rules/bench_families/prepare_record.py` | Paste a contract with a fixed entity type and no classification key. Call `normalize`. A contract that contains `classification` is refused first. |
| 32 | `edgar_warehouse/rules/bench_families/prepare_record_full.py` | Short words for the fixed entity type. Refuse "entity type rule". |
| 33 | `docs/rules-try/prepare_record.md` | The fixed-type case and the missing-key refusal. |
| 34 | `edgar_warehouse/rules/bench_families/prepare_by_type_rule.py` | Paste a contract that has `classification`, and the policy. Call `normalize`. |
| 35 | `edgar_warehouse/rules/bench_families/prepare_by_type_rule_full.py` | The words from 32, plus "entity type rule". This is the only file that accepts that phrase. |
| 36 | `docs/rules-try/prepare_by_type_rule.md` | The rule-decided case. |
| 37 | `docs/engine-rules-primer.md` | One pointer to `docs/rules-try/`. Leave the primitive catalog in the primer. |
| 38 | `docs/engine-rules-reference.md` and the primer | Move the catalog. Leave a pointer where it was. One file-only test that every named primitive exists. |

## Call the function the ticket names

Read that function before writing the family. A same-named function in another module is a different operation.

| Ticket words | Function |
|---|---|
| `SourceEngine.read` | `edgar_warehouse.rules.source_engine.SourceEngine.read` |
| `combine_tables` | `edgar_warehouse.rules.source_engine.combine_tables` |
| reduce finish | the reduce finish the source engine already has; find it, and name it in the ticket's Answer |
| `quality.apply` | `edgar_warehouse.mdm.quality.apply` |
| `classification.classify` | `edgar_warehouse.mdm.classification.classify` |
| `select_fields` | `edgar_warehouse.mdm.survivorship.select_fields` |
| `plan_record_matches` | `edgar_warehouse.rules.source_engine.plan_record_matches` |
| `project` | `edgar_warehouse.mdm.relationships.project` |
| `fold_sightings` | `edgar_warehouse.mdm.relationships.fold_sightings` |
| `normalize` | `edgar_warehouse.mdm.adapters.normalize` |

If the function the ticket names is not in the code, stop. Say which name is missing. Do not invent a stand-in and do not add the method in a second file unless the operator says to.

## Frozen shell

Leave these as they are. A later ticket edits one of them only when a test assertion forces it, and the checklist says so in the same words tickets 02 and 03 used.

- `edgar_warehouse/rules/try_page.py`
- `edgar_warehouse/rules/bench_keep.py`
- `edgar_warehouse/rules/bench_store.py`
- `edgar_warehouse/rules/db.py`
- `edgar_warehouse/rules/cli.py`
- The product folder `edgar_warehouse/rules/bench_families/` starts with `__init__.py` only. A family is the new file the ticket names.

The page command is `edgar-warehouse rules try`. The buttons stay Try, Show the full rule, Keep a copy, and Store this draft.

A family file declares `title` and `inputs`. Each input is `{"name", "label"}`. When the family can be tried, `run(inputs, rule)` returns one JSON object. `<name>_full.py` may declare `words`, a list of `{"word", "stored"}`, and `explain(rule)`. The page loads the short-word file only when the family file exists.

The case is `{family, rule, inputs, expected, actual, passed}`. A refusal is `{"refused": "..."}`. The command exits 1 when the result is exactly `{"refused": "..."}` or when `passed` is false. Keep a copy returns `{"kept": "<path>"}`. Store this draft returns `{"stored", "digest", "status"}` with status `draft`.

Store this draft reads `version` from the pasted rule's JSON. A rule with no version is refused and the database stays closed. A label longer than 128 characters is refused as too long. The label is compared exactly, including case. The case is stored beside the draft. Approve and activate are not called.

Keep a copy writes the case JSON to the path the person confirms with `--path`. No path is refused. A path under `rules/` is refused. A missing folder and a folder path are refused.

## One ticket

- One fresh branch off `origin/main`, prefix `claude/`, in its own worktree. Name the branch new. These names are already used and stay closed: `grok/rules-try-tickets`, `grok/rules-try-page`, `grok/rules-try-keep`, `grok/rules-try-store`, `grok/rules-try-handoff`.
- The primary checkout `/Users/aneenaananth/projects/edgartools-platform` is detached and dirty. Do not commit it, fast-forward it, or run `uv sync` there.
- After `git worktree add -b claude/<name> <path> origin/main`, unset the upstream before any push.
- Claim the ticket (`Status: claimed`) before editing. Resolve it with `## Answer` and `Status: resolved` when every checklist line is checked. Append one line to the map's Decisions so far.
- The ticket names its file. That file is the production change. When a test or the ticket file also has to change, rewrite the "only file" checklist line so it names those files. Tickets 02 and 03 did this.
- A guide ticket adds its markdown file and the ticket. It says "No test."
- Do not edit `rules/`. Do not replace the Rust source engine, the quality engine, or the mastering engine. Do not adopt another rules runtime. Do not switch a stored draft on.
- "attach" is the typed word in two families. The page title tells them apart. Each full-rule file refuses the other family's words.
- Identity consolidation stays on `rules test`. Source priority chooses a field value. It does not decide that two masters are the same subject.
- The word on the page for `kind` is entity type.
- This repository is public. Use the invented examples in the tickets. Never a value from the data. No request to a data provider. Never print a secret, a password, a token, or a database address.
- An integer is `BIGINT`. A decimal stays exact. A same-calendar-day check names `America/New_York`.
- Stamp a finished checklist line with `2026-11-22 11:36 ET`. `bash scripts/dev/commit_push.sh <message-file>` writes the clock's ET time. Never type a time.
- Run `bash scripts/dev/overlap_guard.sh` on its own. Two `claude/` worktrees do not collide. Another runtime editing the same path means stop.

## Proof

Write the failing test first, at the public function the ticket adds (`run`, `explain`, or the guide's words). Expected values are literals from the ticket. Run the tests that change can affect. A local run stays under five minutes. CI runs the rest.

A family ticket that imports `edgar_warehouse.cli.main` needs `uv sync --extra mdm` in that worktree. Test for `.venv/bin/pytest` before `uv run --no-sync`. A guide, primer, or ticket-only change needs no environment. For that change run:

```bash
uv run --no-project --with pytest -- pytest -q -p no:cacheprovider tests/unit/test_profiling_genericity.py
```

After a guide edit, also run `tests/unit/test_guides_name_existing_paths.py` the same way.

Before a production change of more than about ten lines in one function, consult the `gof-refactor-reviewer` skill. After the diff, review Standards, Spec, and GoF. Leave the design in place unless the history shows the change is worth making.

## Pull request

Commit and pull-request text come from files: `git commit -F` and `gh pr create --body-file`. The body has Summary, Evidence, and Merge Danger. Create it with:

```bash
gh pr create --repo paulananth/edgartools-platform --base main --head <branch> --title-file <file> --body-file <file>
```

Then, from that worktree:

```bash
bash scripts/dev/merge_on_green.sh <pr> 90
```

Start that as the background command. It merges the head that CI passed. A push needs no second watcher. Report the pull request URL, the head, and the merge once it lands. Leave the worktree in place.
