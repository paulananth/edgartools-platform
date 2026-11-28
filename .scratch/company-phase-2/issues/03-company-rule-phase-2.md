# The company rule, phase 2

Status: open
Type: task
Owner: claude (map decisions 1 to 6, 8)
Blocked by: 01

A new version of `sec-company-candidate`: no ticker filter; `investment` is a company before the fund-word test; an `other`
filer with a legal-form word is a company unless fund-named, Form-D-only or person-suffixed; commodity pools, asset-backed
issuers and governments stay Set Aside.

## Checklist

- [x] GoF consult (risky-reviewer): a new record test `values_within@1` beside `values_overlap@1`, sharing one helper that reads the list field and the wanted values; no option on `values_overlap@1` (2026-11-27 21:53 ET)
- [x] The person rule's `entity_legal_form` list is kept once, in `rules/merge/lists.yaml`: the policy loader gives each kind the shared lists its rules name, refuses a kind that declares one of the same name, and an export writes them back shared (`tests/unit/test_rules_files.py`, 2 tests). The person kind compiles byte for byte as before (canonical JSON against `origin/main`'s file; its Mapping Document is unchanged) (2026-11-27 21:53 ET)
- [x] `values_within@1`: true when a list field holds a value and every value it holds is listed (`tests/mdm/test_primitives.py`, 2 tests; the engine's Rust tests pass) (2026-11-27 21:53 ET)
- [x] The rule version `2026-11-27.operating-investment-and-legal-form-filers`, named by the contract and `policy.yaml`: steps 1 to 3 (asset-backed, commodity pool, government) unchanged; 4 investment is a company; 5 fund-named operating aside; 8 operating a company; 9 person-suffixed other aside; 10 and 10a unchanged, 10a keeping its ticker (operator, 2026-11-17); 12 fund-named other aside as a probable fund structure; 13 other filing Form D alone aside; 14 other with a legal-form word a company; 15 otherwise aside (2026-11-27 21:53 ET)
- [x] Tests per step: one case per kind of filer, 18 cases (`test_phase_2_masters_every_company_filer_and_sets_aside_the_rest_with_its_probable_kind`; on today's rule it fails at its first case, a tickerless operating filer held back at step 0); company tests 7 passed, rule-related unit and MDM tests 1,059 passed (2026-11-27 21:53 ET)
- [x] Proved with the real engine on the hosted store's 69,756 held-back company filers, read only (23 s): 19,212 become companies (step 14 16,566, step 4 1,793, step 8 803, step 10 50); aside: step 15 31,964, step 13 9,083, step 12 7,510, step 1 1,062, step 9 658, step 2 149, step 5 86, step 3 32. The 6,474 stored company filers came through steps 8 (5,091), 10 (1,159) and 10a (224), whose tests are unchanged. Gold's 976 unlinked company CIKs: 702 become companies through the company feed (21 of them already companies through N-CEN or N-PORT), 102 more are companies already through N-CEN or N-PORT, 170 stay aside (126 commodity pools), and 2 the feed never held (ticket 07). The simulation's own logic over the same records gives 19,199; the rule differs from it on 13 records, each a name the engine's `&` rule or conformed name reads as legal-form that the simulation's plain tokens did not. The 18,645 quoted at grilling could not be reproduced (2026-11-27 21:53 ET)
- [x] `/code-review`, three axes on `risky-reviewer`. GoF: leave it. Standards: no rule broken; fixed: a kind takes a shared list only by a test's list argument (`token_list`, `suffix_list`, `exclude_list`, `values`), not by any text; the company test asserts the shared list is present instead of copying the merge; the rule and test state what is; step 14 says why `&` counts; Left: the kind workbook's Notes sheet does not carry `lists.yaml`'s comment. Spec: nothing missing; added tests for every 10a form and an empty entity type (aside at 15); one fund-named filer becomes a company at step 10 (a 20-F filer: steps 10 and 10a come before the fund-word step, as the 2026-11-14 and 2026-11-17 rulings placed them), no Form-D-only operating filer and no other entity type among the 69,756. Tests 163 passed (2026-11-27 21:53 ET)
- [ ] ~~`docs/engine-rules-primer.md` lists `values_within@1`~~ deferred until Codex's open worktree `codex/rules-try-ui-progress-20261127`, which changes that file, merges (overlap guard)
- [x] The operator's approval of the version against that evidence (operator, "yes", recorded 2026-11-27 22:07 ET): it masters every SEC filer that is a company, with or without a ticker, as decisions 2 to 6 and 8 say; the words are on the rule in `company.yaml` (2026-11-27 22:07 ET)
- [x] Learning → skill: `skills/refining-rules/SKILL.md`, a word list two kinds read lives once in `rules/merge/lists.yaml` (2026-11-27 21:53 ET)
