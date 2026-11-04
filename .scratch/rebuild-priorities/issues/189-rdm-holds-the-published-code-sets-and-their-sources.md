# 189: RDM holds every published code set, and each set's source is written down

Priority: 189. Map: [Rebuild priorities](../map.md). Opened 2026-11-03 20:27 ET, from the operator: "load rdm use skills", then "find the source of each rdm code set and reload update skills with source".

Type: task. Status: resolved. Blocked by: none.

## Question

The shared RDM database was empty (`rdm list` returned `[]`) while 11 code sets are pinned by the policy in `rules/reference/published/`. Those files keep a version's codes and sha256 but not the set's name, definition, authority or source. Where did each set come from, and how does an empty RDM reload from the repository?

## Parts

- [x] (2026-11-03 20:27 ET) The source of each code set found in its ticket and draft script (SEC place codes and Form 4 codes, OpenFIGI answers, ISO 10383, N-PORT 2026 Q2 currencies, SEC submissions' SIC codes, OECD tax rates, the line-item map, the relationship-type tables): recorded in `WORDS` in `scripts/dev/reload_rdm.py` and the `WORDS` and the "RDM code sets and their sources" sections of the security-master and company-financials skills
- [x] (2026-11-03 20:27 ET) The shared RDM database reloaded: 12 versions of 11 code sets drafted, approved under the operator's reload words ("load rdm use skills") with each set's first approval words kept in its evidence, published into a temporary folder; every version's bytes and sha256 equal the repository's file and pin (the script refuses otherwise); `rdm list` shows 11 sets, with `mdm-relationship-types` at version 2
- [x] (2026-11-03 20:27 ET) `tests/unit/test_reload_rdm_words.py` (2 passed): every published version has its words, and a crosswalk target loads before the set that points at it
- [x] (2026-11-03 20:27 ET) Learning → skill: `skills/data-operations/SKILL.md` "Reload RDM", and "RDM code sets and their sources" in `skills/security-master/SKILL.md` and `skills/company-financials/SKILL.md` (the other sources are in each set's authority in RDM and in `WORDS`; the genericity lint keeps other skills free of source names): a published folder keeps no words, so a new code set adds its row and its `WORDS` entry in the same change
- [ ] ~~Crosswalk targets RDM does not hold (`iso-3166`, `iso-3166-alpha-3`, `openfigi-exchange-codes`, and the line items' reported concepts)~~ deferred: they are outside standards the sets point at with version `outside`; their own code sets are a separate decision
