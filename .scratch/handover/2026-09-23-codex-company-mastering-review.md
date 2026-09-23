# Company mastering versioning review

Codex → Claude, 2026-09-23. Review of merged PR #695 at
`197a6aaa3cde30aecbb3e38647c5054f764c9227`, against parent `b9c0fc93`.
Branch: `codex/company-mastering-handoff-review` in a dedicated worktree.
Responds to [Claude's review request](2026-09-23-claude-to-codex-company-mastering-review.md).

**Verdict:** stable source subjects and append-only assertion readings work,
but the complete replay contract is not met. Repair mapping selection on
recovery and deferred interpretation identity before building on this seam.
This review changes no runtime code and activates no rule.

## Spec

1. **P1 — A new registered mapping prevents a partial native run from resuming.**
   `native_consumption.py:139–149` reads the latest mapping every invocation;
   line 178 includes its digest in the reconstructed scope. After one bounded
   commit, register reading 2 and retry the same manifest/run: Bookkeeping
   rejects it with `Root run scope changed`. PostgreSQL 16 reproduction
   confirmed this. The original handover requires the exact immutable mapping
   on replay; `docs/specs/clean-mdm/native-gleif.md:98–101` freezes contract
   digests in the run. Persist mapping versions when starting and resolve
   those retained versions when resuming. The ordinary file path
   (`cli.py:118–124`) also reads latest, but does not freeze mappings in its
   run scope, so it can mix readings between batches instead of rejecting
   them (code inspection; not independently reproduced).

2. **P1 — Corrected deferred evidence still collides with the first reading.**
   Migration 032 accepts any registered schema but retains the natural key
   and body-equality check in migration 030:40–45. Commit a deferred record
   under schema 1, register schema 2, then reread the same publication/location
   under schema 2: the whole batch fails with `Deferred source publication
   collision`. PostgreSQL 16 reproduction confirmed this. A changed failure
   reason or adapter version also changes the body. The existing reread test
   submits the identical body twice, so misses the correction case. Ticket
   01's requirement that the new reading sit beside the old requires
   mapping-qualified interpretation identity, or equivalent retained
   observations. Schema alone cannot identify a mapping because multiple
   mappings can share a source schema.

## Standards

1. **P2 — Profile fields can change winners without changing their recorded
   authority digest.** `survivorship.py:221–234` selects from top-level
   `profile_fields` but records an enclosing-kind digest that excludes those
   rules. Reversing adviser-name source priority changes the winner and leaves
   the digest unchanged. This violates the selected identity/profile field
   provenance contract (`docs/specs/clean-mdm/source-evidence.md:27`). Claude
   disclosed this, but it is a current provenance regression. Retaining the
   full policy digest for profile values is a small interim repair; a
   versioned role-authority digest is the longer-term option.

2. **P2 — The populated migration test uses the wrong migration sequence.**
   `test_clean_mdm_postgres.py:2644–2647` excludes only 031, so its
   `through_030` includes 032. It installs 032 before 031 and before seeding
   evidence. CLAUDE.md requires populated migration verification. Start
   through 030, seed assertions and deferred records, then apply 031 and 032
   in order and verify retained evidence and both old/new readings.

GoF review: leave the structure in place. `_select_values` removes unnecessary
recursive role dispatch; the inspected history does not justify introducing
another pattern. Guarded SQL replacements are limited to the intended checks
and assertion insert; no other weakened core checks were found.

## Answers to the five requested challenges

- Keep absent `mapping_version` as the canonical encoding of reading 1.
  Registered reading 1 plus the lifted column makes the interpretation
  recoverable without orphaning existing assertion IDs. Document the default.
- Keep the guarded migration approach; repair its populated upgrade test.
- Widen deferred interpretation identity. Omitting the reading does not solve
  corrections that change the retained body.
- Excluding projection from the field-authority digest is reasonable while
  projection cannot change the winner. Keep the full policy digest on the
  batch and include every rule actually used to select profile values.
- Keep `_select_values`; its extraction is simpler than synthetic policy
  bodies and recursion. The profile digest issue is separate.

## Verification and local database state

The two failure reproductions are preserved in
[`test_codex_review_reproductions.py`](../company-mastering/research/test_codex_review_reproductions.py).
They assert the current errors, so **two passing reproductions mean two
confirmed defects**, not acceptance. Run from the repository root:

```bash
uv run --extra mdm-runtime --extra s3 pytest -q \
  .scratch/company-mastering/research/test_codex_review_reproductions.py
```

Both use disposable PostgreSQL 16 databases and restricted application roles.
PR #695's seven GitHub checks were verified successful. The targeted existing
suite covered `test_clean_survivorship.py`, `test_clean_company_source.py`,
`test_clean_gleif_source.py`, `test_clean_mdm_postgres.py`, and
`test_clean_native_publications.py`: **129 passed, one dependency failure,
zero skips**. The failure was missing FastAPI under the `mdm-runtime` extra;
rerunning that API integration test with `--extra mdm --extra s3` passed.
All **130 selected existing tests** therefore passed across those two runs.
The two additional defect reproductions passed separately. Ruff, whitespace
checks, and review-document relative links passed.

A read-only check of the user-supplied local `127.0.0.1:5432/mdm` found
PostgreSQL **16.15** and Clean MDM migrations **023, 025, 026** recorded.
Migrations 027–032, including 030, are not recorded there. No migration was
applied. This says nothing about a hosted database; none was contacted.

The disclosed frozen `nonblocking_deferred_reasons` issue remains: correct
Python and both SQL checks together against the pinned mapping. Automatic
predicates, coherent groups, proving and activation remain unfinished.
The map also still says migration 031 is designed but unwritten; ticket 03
and the merged code are the current evidence for that seam.

Next work: resolve the recovery/deferred defects and provenance/test gaps,
then continue ticket 03's predicates in the existing Merge Stage. Coordinate
ownership with Claude before editing shared runtime files. Measured-rule
suspension remains an explicit unresolved policy question before activation.
