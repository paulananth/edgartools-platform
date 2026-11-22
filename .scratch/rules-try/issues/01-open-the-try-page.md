# Open the try page

Type: task
Status: open
Label: ready-for-agent
Blocked by: none

## What to build

Add the try page and nothing else. This is the only ticket that creates more than one file. Later tickets do not edit these files.

Command: `edgar-warehouse rules try`. Buttons, fixed: Try, Show the full rule, Keep a copy, Store this draft.

The page shows the inputs the family declares, the rule, and the expected output. The title is the title that family declares. A family appears when `bench_families/<name>.py` exists. `<name>_full.py` is used only when that run file also exists. Compare is JSON equality. The result is one JSON object. A refusal is `{"refused":"..."}`. Keep a copy and Store this draft refuse until tickets 02 and 03 replace their files.

Owns: the page module, empty `bench_families/`, `bench_keep.py`, `bench_store.py`.

## Checklist

- [ ] The page, the empty family folder, and the two refuse files exist
- [ ] `rules try` shows inputs, the rule, and the expected output
- [ ] A family appears only because its file exists
- [ ] A temp-folder fake family shows its title and input labels
- [ ] Compare ignores key order
- [ ] Keep a copy and Store this draft refuse
- [ ] No engine call, no `rules/` read, and no database
- [ ] Learning → skill

## Comments

