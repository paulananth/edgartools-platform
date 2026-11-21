# 12: The Gold configuration is a destination, not a rule

Status: resolved
Type: task

Operator, 2026-11-21: "move rules/gold to destination/gold". Where Gold is written is not a rule, as sources were not (ticket 11).
One file, `gold.yaml`, read only by `edgar_warehouse/gold/views.py`.

## Checklist

- [x] Test first: `test_the_gold_configuration_is_a_destination_not_a_rule` failed (`views.CONFIG` was `rules/gold/gold.yaml`), passes now 2026-11-21 08:04 ET
- [x] `git mv rules/gold destination/gold`; `views.CONFIG` reads `destination/gold/gold.yaml` beside the rules folder; every text reference follows (the views, the dbt project, the managed mirror record) 2026-11-21 08:04 ET
- [x] Packaging: `pyproject.toml` include, the data-skill wheel's `destination` mapping, `skill install --rules` copies `destination` beside the rules 2026-11-21 08:04 ET
- [x] Tests: Gold views 25, architecture, bundle and catalog unit tests pass; the merge policy digest does not read this file. The catalog's display digest (a hash of every file under the rules folder) changes once, because `gold.yaml` leaves it; the policy digest and every source's rules version are unchanged 2026-11-21 08:04 ET
- [x] Learning → skill: none; the skills name `gold.yaml` by file, not by folder 2026-11-21 08:04 ET

## Answer

`destination/gold/gold.yaml` replaces `rules/gold/gold.yaml`; nothing else reads it.
