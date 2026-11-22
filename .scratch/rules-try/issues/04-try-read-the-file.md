# Try Read the file

Type: task
Status: open
Label: ready-for-agent
Blocked by: 01

## What to build

Add `bench_families/read_file.py` only. The person pastes a read document, the file bytes, and any lookup lists. The page calls `SourceEngine.read`. Do not open a capture folder.

Invented pass: `{"records":[{"id":"R1","name":"  Example Works  ","quantity":"12"}]}` becomes one row `{"id":"R1","name":"Example Works","quantity":12}`. A bad paste returns `{"refused":"..."}`.

## Checklist

- [ ] `read_file.py` is the only file this ticket adds
- [ ] The invented R1 row matches the expected output
- [ ] A bad paste is a refusal object, not a traceback on the page
- [ ] No capture folder is opened
- [ ] Learning → skill

## Comments

