# 07: RDM publishes one view per code set

Status: open

The operator, 2026-11-20: "Rdm has to publish views on types this must be in the skills"; asked where, chose
"One per code set, in Gold (Recommended)". Then, told the view showed the latest of several versions: "there should
not be more than one version now".

## Checklist

- [x] Skill first: data-modeling GOLD.md "RDM publishes one view per code set"; FINAL-TABLES.md points to it; skill lints pass 2026-11-20 09:54 ET
- [x] Gold makes `ref_<code set>` for each folder of `rules/reference/published/`, selecting that folder's one version by name over `rdm.published_code`; a folder with two versions is refused; `tests/unit/test_gold_views.py` 2026-11-20 09:54 ET
- [x] A code set keeps one version: GOLD.md says so; `mdm-relationship-types` versions 1-4 and the history set `mdm-relationship-types-before-real-names` deleted (version 5 kept under its pinned number); the four version-diff tests replaced by one that states version 5's approved changes; both RDM loaders load one version per set. Failed before the fix: `test_every_published_code_set_holds_exactly_one_version` (`mdm-relationship-types: 5 != 1`); 239 affected unit tests and 1172 `tests/mdm` pass 2026-11-20 09:54 ET
- [x] The hosted RDM holds the same 11 code sets as the repository's folders (read as the owner: none missing either way) 2026-11-20 09:54 ET
- [x] Mirror test: Gold now reads 19 tables, `rdm.published_code` among them (`tests/unit/test_exposure_mirror_sql.py`) 2026-11-20 09:54 ET
- [x] `ALTER_MIRROR` added `rdm.published_code` and the 14 silver tables (operator: "use ANANP11"; words in the approvals log): "Mirror altered", read back as 18 tables listed while the copy runs 2026-11-20 09:54 ET
- [ ] Read back: 19 tables `REPLICATING`
- [ ] ~~Hosted RDM still holds the six old versions (111 published code rows of `mdm-relationship-types` 1-4 and the history set)~~ deferred to its own ticket: the store keeps a retired version's rows by design and has no command that removes a version; the views cannot show them, since each selects its one version by name
- [ ] Learning → skill: data-modeling GOLD.md, "RDM publishes one view per code set"
