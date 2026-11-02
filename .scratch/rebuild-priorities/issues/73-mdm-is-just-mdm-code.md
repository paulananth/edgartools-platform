# MDM is just MDM: the code names

Priority: 73, tier 4, housekeeping (numbered after the map was charted). Map: [Rebuild priorities](../map.md). Moved from `.scratch/mastering-to-done/issues/27-mdm-is-just-mdm-code.md` on 2026-10-13.

Status: parked (operator, 2026-11-02: "Leave it parked"), except parts 3 and 5, done at the operator's word ("Fix ... 3 ... and 5"). The ownership blocker named here (a Grok branch) was deleted on 2026-11-02; check the overlap guard before parts 1, 2, 4 and 6.
Blocked by: none (mastering-to-done 26 merged as #956)

The second half of the operator's "Purge Clean from MDM" (2026-10-13). Each part needs a GoF consult first, and a check that no Codex PR touches the files.

- [ ] The package `edgar_warehouse/mdm/clean/` merges into `edgar_warehouse/mdm/` (33 files, 177 importers)
- [ ] The 57 test files named `test_clean_*` are renamed
- [x] The Data Catalog's `CLEAN` schema constant is `MASTER_RECORDS` (the schema `mdm.master_records`; tests in `tests/unit/test_rules_catalog.py`), and the publication format id is `mdm-publication-v2` (the same format under its new name; only two spec files named it, no stored manifest does) (2026-11-02 18:00 ET). The live catalog still lists the old schema `clean` until the next publish removes it
- [ ] The environment variables `BOOKKEEPING_CLEAN_*` and their install.sh and secret names
- [x] The local names (2026-11-02 18:00 ET): the container and volume are `edgartools-mdm-pg16` and `edgartools-mdm-pg16-data` (`infra/scripts/start-local-postgres.sh`; none existed here); the test-container prefix `clean-mdm-test-` was stale (test stores are `edgartools-local-<name>`), so the data-onboarding skill names that; the data folder `~/.local/share/edgartools/clean-mdm/` moved to `~/.local/share/edgartools/mdm/` and four references follow. The recorded qualification evidence (`sec-population.json`) keeps the old folder in its URIs, and `.scratch/clean-mdm/` history keeps its name
- [ ] A rules version whose comments drop the word, approved by its digest
- [ ] PR, CI green, merge on the operator's word
