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
  `docs/specs/mdm/policy-language.md` names the new folder.
- [x] Ship `rules/` in both images: `COPY rules /app/rules` (2026-09-26
  15:55 ET). The images run from `/app`, so `files.ROOT` resolves to
  `/app/rules`. `RULES_ROOT` overrides it.
- [x] Tests (2026-09-26 15:57 ET; 155 passed with the affected
  `test_clean_company_source.py` and `test_clean_gleif_source.py`):
  - `tests/unit/test_rules_files.py`: exact round trip for tricky values, and
    refusals with line numbers;
  - `tests/mdm/test_rules_config_digests.py`: every digest unchanged, and
    every rules file round-trips;
  - `tests/architecture/test_rules_files_ship.py`: the images copy `rules/`,
    and `.dockerignore` keeps it.
- [ ] Unit/architecture, `tests/mdm` and the full Clean PG16 suite pass.
- [ ] Three-axis `/code-review`, then PR and CI.
