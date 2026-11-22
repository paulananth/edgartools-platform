# Try Group and attach rows

Type: task
Status: open
Label: ready-for-agent
Blocked by: 01

## What to build

Add `bench_families/group_rows.py` only. The person pastes the plan and the input tables. The page calls `combine_tables`. Do not import `read_file.py`.

Invented pass: row `R1` with names `B` then `A` produces aliases `["A","B"]`.

## Checklist

- [ ] `group_rows.py` is the only file this ticket adds
- [ ] The R1 alias case matches `["A","B"]`
- [ ] This file does not import `read_file.py`
- [ ] Learning → skill

## Comments

