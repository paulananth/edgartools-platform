# Rules files; production loads them

Type: task
Status: claimed (Claude, branch `claude/rules-p1-files`, 2026-09-26 15:49 ET)
Blocked by: none

## Outcome

The SEC Company and GLEIF MDM mappings and the Company merge rules live in
`rules/` files, and production code loads them from there. The Python and
JSON copies are gone. Every digest is unchanged, so behaviour is unchanged
(live Company policy `983352e8…4049`). No database and no new dependency.

## Checklist (times ET)

- [x] `/gof-refactor-reviewer` on `company_source.py`, `gleif_source.py` and
  `policies/` (2026-09-26 15:50 ET). **Verdict:** move as-is; the move is the
  fix. The config changed 6, 5 and 4 times in 7 days, always as data, and the
  same change touched all three files (#706, #713, #714). GLEIF's member
  `if/elif` disappears into data (one `mdm` key per member). Keep
  `compose_policy()` and `name_matching_policy()` as small functions. Write
  each GLEIF member out in full; no YAML anchors or inheritance (spec §25
  Open).
- [x] Record every digest before the move (2026-09-26 15:51 ET): `POLICY`
  `983352e8…4049`, `CONTRACT`, `FIELDS`, `PROOF`, `APPROVED_ACTIVATION`,
  `NAME_PROOFS`, both `name_matching_policy` forms, and each GLEIF member's
  contract. They are pinned in `tests/mdm/test_rules_config_digests.py`.
- [x] `edgar_warehouse/rules/files.py` (2026-09-26 15:53 ET; verified by
  `tests/unit/test_rules_files.py`, 50+ cases). It has a strict loader:
  - an unquoted `null`, `true`, `false` or JSON number is typed;
  - any other unquoted value YAML would type is refused, with its line;
  - everything else, and every key, is text;
  - duplicate keys, anchors, aliases, tags and a second document are refused.

  The writer quotes any string the loader would not read back as itself.
- [x] Wrote the files from today's values with the writer (2026-09-26 15:54 ET),
  then added the Python comments as YAML comments:
  - `rules/merge/policy.yaml` (the envelope);
  - `rules/merge/kinds/company.yaml` (was `company.json`);
  - `rules/merge/pending-proofs.yaml` (was `NAME_PROOFS`);
  - `rules/sources/sec.submissions.company/source.yaml`;
  - `rules/sources/gleif/source.yaml`, with one `mdm` key per member.

  Kind files sit in `merge/kinds/`, so the envelope and pending proofs need no
  special names. Verified: every digest read from the files equals its value
  before the move.
- [x] `company_source.py` and `gleif_source.py` load from the files and keep
  their public names (2026-09-26 15:55 ET). GLEIF's member `if/elif` became a
  lookup by `native_member`. Deleted `edgar_warehouse/mdm/policies/`. The
  `pyproject.toml` include now names `rules/**/*.yaml`.
  `docs/specs/mdm/policy-language.md` names the new folder. Verified by
  `tests/mdm/test_rules_config_digests.py` (the loaded names equal their
  digests before the move) and `test_clean_company_source.py`/
  `test_clean_gleif_source.py`.
- [x] Ship `rules/` in both images: `COPY rules /app/rules` (2026-09-26
  15:55 ET). The images run from `/app`, so `files.ROOT` resolves to
  `/app/rules`. Verified 16:05 ET: built `Dockerfile.mdm-neo4j` locally on
  the cached `mdm-deps-1b3db75385592471` and ran it. `files.ROOT` is
  `/app/rules`, the policy digest is `983352e8…4049`, the contract digest is
  `6d833beb…`, and the pending proofs digest is `42e7b849…`. That deps image
  is older than the lock and has no `ijson`, so importing `company_source`
  inside it fails on `main` too. That is unrelated to this change. A wheel
  (`uv build`) holds `rules/` beside `edgar_warehouse/`, which is where
  `files.ROOT` looks.
- [x] Tests (2026-09-26 15:57 ET; 155 passed with the affected
  `test_clean_company_source.py` and `test_clean_gleif_source.py`):
  - `tests/unit/test_rules_files.py`: exact round trip for tricky values, and
    refusals with line numbers;
  - `tests/mdm/test_rules_config_digests.py`: every digest unchanged, and
    every rules file round-trips;
  - `tests/architecture/test_rules_files_ship.py`: the images copy `rules/`,
    and `.dockerignore` keeps it.
- [x] Suites on the fixed code: unit/architecture 1,988 passed, 4 skipped
  (2026-09-26 16:12 ET); `tests/mdm` 1,121 passed (16:14 ET). The Clean PG16
  suite is left to CI's integration job (`ci.yml`, `tests/integration/` on
  PG16): the operator asked why a skill needs local Python runs, and CI
  runs the same suite on the PR.
- [x] Three-axis `/code-review` (2026-09-26 16:07 ET). GoF: no findings; its
  notes for ticket 02 are recorded there. Fixed:
  - collection tags (`!!map`, `!!seq`, `--- !!map`) crashed with a
    `TypeError`; every tag is now refused with its line, and tested;
  - removed the `RULES_ROOT` override: nothing used it, and it would let the
    environment swap the digest-pinned rules;
  - `gleif_source.dataset_contract` keeps the file's Level 1 source unless a
    caller names another one;
  - absolute imports of `edgar_warehouse.rules`;
  - `pending-proofs.yaml` again records the operator's approval of the
    ticket 08 rules as declared rules at policy `983352e8…`;
  - `plan.md` names the layout as built (`merge/kinds/`,
    `merge/pending-proofs.yaml`, `policy()`, keys as text);
  - `CLAUDE.md`: a Quick Navigation row and an image rebuild row for `rules/`;
  - `.scratch/company-mastering/research/08-parity.py` reads the rules files.

  Not fixed, by design: `.scratch/company-mastering/research/12-classify.py`
  still imports `edgar_warehouse.mdm.policies`. Its sha256 is pinned inside
  the live policy's proof (`PROOF.cohort.files`), so an edit would change
  `983352e8…`. To rerun it, check out the commit before this change.
- [ ] PR and CI.
