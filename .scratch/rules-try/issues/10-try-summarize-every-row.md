# Try Summarize every row

Type: task
Status: open
Label: ready-for-agent
Blocked by: 01

## What to build

Add `bench_families/whole_set.py` only. The person pastes the reduce plan and the rows. The page calls the existing reduce finish. Do not import `group_rows.py`.

Invented pass: three rows, two of them the same member, produce that count, those distinct values, and that most-frequent value. A two-way tie produces a blank for most frequent.

## Checklist

- [ ] `whole_set.py` is the only file this ticket adds
- [ ] The three-row case matches the count, the distinct values, and the most-frequent value
- [ ] A two-way tie is blank
- [ ] This file does not import `group_rows.py`
- [ ] Learning → skill

## Comments

