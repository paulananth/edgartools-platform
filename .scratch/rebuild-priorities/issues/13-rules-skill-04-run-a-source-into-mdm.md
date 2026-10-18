# Run a source into MDM

Priority: 13, tier 2, the recreation proof. Map: [Rebuild priorities](../map.md). Moved from `.scratch/rules-skill/issues/04-run-a-source-into-mdm.md` on 2026-10-13; a Blocked by list of numbers now uses this map's numbers (or names the old effort); free text keeps the old effort's numbers.

Type: task
Status: closed, the rest moved to ticket 12 (2026-10-18). Was partly built: `rules run` submits configured runs. Preview, validate and `rules test` moved to `mastering-to-done/issues/09-test-check-and-preview-for-onboarding.md` (2026-10-02 audit, mastering to-do 01).
Was: open
Blocked by: rules-skill 02, rules-skill 03

## Outcome

`rules run <source> --target mdm` with `--preview`, `--validate` and
`--deploy`, plus `activate` and `adopt`. Preview runs on a throwaway copy of
the local MDM. Validate is the Proving Run and marks the version proven.
Activate needs the operator's approval for anything that feeds MDM, and it is
the only command that registers into Clean MDM. Deploy runs the Merge Stage.

## Checklist (times ET)

- [ ] ~~`/gof-refactor-reviewer` before code.~~ moved to ticket 12 (2026-10-18 12:25 ET): `rules run` and `rules activate` exist; Preview, validate, adopt and `rules test` are ticket 12's
- [ ] ~~Parse to `records.jsonl` plus a manifest, then call `execute_manifest`~~ moved to ticket 12 (2026-10-18 12:25 ET): `rules run` and `rules activate` exist; Preview, validate, adopt and `rules test` are ticket 12's
  (limits: at most 1,000 records and 16 MiB).
- [ ] ~~Preview on a copy of local `mdm`, falling back to an empty database.~~ moved to ticket 12 (2026-10-18 12:25 ET): `rules run` and `rules activate` exist; Preview, validate, adopt and `rules test` are ticket 12's
  Writes nothing to the real store.
- [ ] ~~Validate: tests, checks, merge cases and the gate, then `proven`.~~ moved to ticket 12 (2026-10-18 12:25 ET): `rules run` and `rules activate` exist; Preview, validate, adopt and `rules test` are ticket 12's
- [ ] ~~Activate:~~ moved to ticket 12 (2026-10-18 12:25 ET): `rules run` and `rules activate` exist; Preview, validate, adopt and `rules test` are ticket 12's
  - builds the approval-stamped D′;
  - stamps the Source Contract digest into the contract when the source has
    a `read` section;
  - registers into Clean MDM first, then flips status.
- [ ] ~~`adopt`: the live SEC Company, GLEIF and Company policy versions become~~ moved to ticket 12 (2026-10-18 12:25 ET): `rules run` and `rules activate` exist; Preview, validate, adopt and `rules test` are ticket 12's
  active by proving parity with `mdm_v2`.
- [ ] ~~Tests:~~ moved to ticket 12 (2026-10-18 12:25 ET): `rules run` and `rules activate` exist; Preview, validate, adopt and `rules test` are ticket 12's
  - preview writes nothing;
  - activate is refused without approval;
  - deploy is refused for a version that isn't active;
  - a parse-only change mints a new reading;
  - a rerun after a registry version bump.
- [ ] ~~Three-axis `/code-review`, then PR and CI.~~ moved to ticket 12 (2026-10-18 12:25 ET): `rules run` and `rules activate` exist; Preview, validate, adopt and `rules test` are ticket 12's
