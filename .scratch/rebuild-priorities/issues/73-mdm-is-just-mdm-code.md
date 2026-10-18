# MDM is just MDM: the code names

Priority: 73, tier 4, housekeeping (numbered after the map was charted). Map: [Rebuild priorities](../map.md). Moved from `.scratch/mastering-to-done/issues/27-mdm-is-just-mdm-code.md` on 2026-10-13.

Status: open, waits for an ownership decision (2026-10-18 18:04 ET): Grok's branch `grok/data-operations-stores` (no PR, last commit 2026-10-17) changes 11 files that import `edgar_warehouse.mdm.clean`; moving the package breaks that branch, so the operator decides who goes first (CLAUDE.md, overlap).
Blocked by: none (mastering-to-done 26 merged as #956)

The second half of the operator's "Purge Clean from MDM" (2026-10-13). Each part needs a GoF consult first, and a check that no Codex PR touches the files.

- [ ] The package `edgar_warehouse/mdm/clean/` merges into `edgar_warehouse/mdm/` (33 files, 177 importers)
- [ ] The 57 test files named `test_clean_*` are renamed
- [ ] The Data Catalog's `CLEAN` schema constant, and the publication format id `clean-mdm-publication-v1` (a versioned contract: needs a new version, not an edit)
- [ ] The environment variables `BOOKKEEPING_CLEAN_*` and their install.sh and secret names
- [ ] The local names: the container `edgartools-clean-mdm-pg16`, the test-container prefix `clean-mdm-test-`, and the data folder `~/.local/share/edgartools/clean-mdm/`
- [ ] A rules version whose comments drop the word, approved by its digest
- [ ] PR, CI green, merge on the operator's word
