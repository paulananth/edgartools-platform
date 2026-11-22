# Move the primitive catalog out of the primer

Type: task
Status: open
Label: ready-for-agent
Blocked by: 01, 37

## What to build

Add `docs/engine-rules-reference.md`. Edit the primer only to remove the catalog this ticket is moving, and leave a pointer where the catalog was. Add one file-only test that every named primitive exists. Do not edit a family file or the shell.

This ticket waits for 37 because both edit the primer.

## Checklist

- [ ] The catalog lives in `docs/engine-rules-reference.md`
- [ ] The primer points at that file where the catalog was
- [ ] A file-only test checks that every named primitive exists
- [ ] No family file and no shell file is edited
- [ ] Learning → skill

## Comments

