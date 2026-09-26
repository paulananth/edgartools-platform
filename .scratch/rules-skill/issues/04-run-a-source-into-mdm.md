# Run a source into MDM

Type: task
Status: open
Blocked by: 02, 03

## Outcome

`rules run <source> --target mdm` with `--preview`, `--validate` and
`--deploy`, plus `activate` and `adopt`. Preview runs on a throwaway copy of
the local MDM. Validate is the Proving Run and marks the version proven.
Activate needs the operator's approval for anything that feeds MDM, and it is
the only command that registers into Clean MDM. Deploy runs the Merge Stage.

## Checklist (times ET)

- [ ] `/gof-refactor-reviewer` before code.
- [ ] Parse to `records.jsonl` plus a manifest, then call `execute_manifest`
  (limits: at most 1,000 records and 16 MiB).
- [ ] Preview on a copy of local `mdm`, falling back to an empty database.
  Writes nothing to the real store.
- [ ] Validate: tests, checks, merge cases and the gate, then `proven`.
- [ ] Activate:
  - builds the approval-stamped D′;
  - stamps the Source Contract digest into the contract when the source has
    a `read` section;
  - registers into Clean MDM first, then flips status.
- [ ] `adopt`: the live SEC Company, GLEIF and Company policy versions become
  active by proving parity with `mdm_v2`.
- [ ] Tests:
  - preview writes nothing;
  - activate is refused without approval;
  - deploy is refused for a version that isn't active;
  - a parse-only change mints a new reading;
  - a rerun after a registry version bump.
- [ ] Three-axis `/code-review`, then PR and CI.
