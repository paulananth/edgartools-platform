# One self-sustaining data skill

Type: task (code and skill), several PRs
Status: in progress (Claude, branch `claude/data-skill-bundle`)
Blocked by: none for the bundle (G1, G2, G5); G3 needs 20e and the Company and GLEIF read blocks (20 L3–L6)
Absorbs: 20 L3–L8 (Codex's list: SEC Company and GLEIF on the engine), 16, 17

## Request

Operator goal, 2026-10-03: "update skills 1) the skills must be self sustaining 2) must bundle rules creator 3) must be able to orchasgrate 1) the parsing 2) mdm 3) custom parsing if needed ask questions to finalize goals".

Operator, 2026-10-02 (mid-turn): "continue to complete the list from codex and test it again from the begining".

Answers, 2026-10-03:
- Self-sustaining: "One installable bundle (Recommended)". This is one skill folder that brings its own package: the rules creator, the engine, Bookkeeping and MDM. Any agent installs it and runs it with no repo checkout. It has one entry point, onboard → parse → MDM → custom parsing only when needed, and it checks its own commands and documents.
- Custom parsing: "Write a step, then stop (Recommended)". The skill drafts one plain function and its tests and lists the step in the Mapping Document. It runs the step in a test run, opens a PR and stops for the operator's approval. It never switches on custom code.
- Ownership: "codex finished and pr created and merges now claude take over and finishes". Codex's #804 merged at 07:09 ET. Claude now owns the engine, the workers and the rest of Codex's list.

## Reading

- **Rules creator:** the `rules` commands (init, migrate, load, unload, mapdoc, catalog, pending, save, status, export, record-proof, approve, activate, run), together with the onboarding steps that write `rules/` files. `profile`, `check` and Preview are not built (ticket 09). The skill says so and gives the step to do by hand.
- **One skill, four old names kept.** `data-onboarding`, `refining-rules`, `bookkeeping` and `change-journal` stay as thin entries into the bundle, because Codex and Grok load them through `link.sh`. Their reference files (APPROVE, REFERENCE, RUN, RECOVERY) are linked, not copied.
- **No orchestration loop inside Bookkeeping.** Control stays control only (20a). The loop that runs the workers lives on the bundle's worker side.
- **Custom parsing needs a git checkout.** A custom step is code in `steps.py`, reviewed in a PR. Every other mode needs no checkout.

## Gates: done means each is proved by a test

- **G1, self-sustaining:** installed from a pinned git ref into a clean environment, with no checkout, `doctor` passes. Isolated mode, with `edgartools` and `spacy` blocked.
- **G2, rules creator:** the rules commands run from the installed bundle against an empty Rules Database.
- **G3, orchestration:** on empty PostgreSQL 16 stores, a real source runs through parse (`source.read`) and then MDM, through the installed bundle.
- **G4, custom parsing:** the custom-step mode drafts a step and its tests, runs a test, opens a PR and stops.
- **G5, no drift:** a CI test fails when a command or path named in a skill does not resolve against the installed command line.

## Checklist

- [x] Questions asked and answered (three above). 2026-10-03 07:22 ET
- [x] Ownership change written where Codex reads it: `docs/research/custom-parsing-implementation-notes-2026-10-02.md` (the 13F ticket is complete, so it is unchanged). 2026-10-03 07:22 ET
- [x] Packaging facts, by running them: the Bookkeeping and Journal wheels install from a `git+file://…@<sha>#subdirectory=` ref (11 s), so `../../` force-include survives; the engine installs the same way when `cargo` is present (1 min 43 s; maturin comes from its build requirements). 2026-10-03 07:40 ET
- [x] GoF consult: leave the structure; include folders a wheel owns whole and guard the three-wheel partition with a test (20b shipped files in two wheels twice); `orchestrate` later as a plain function in `workers/`. 2026-10-03 07:45 ET
- [x] Bundle: `packages/data-skill` (`edgartools-data`), command `edgar-warehouse` (one entry point, not a new name): `rules`, `bookkeeping`, `change-journal`, `mdm`, `workers` (was `python -m edgar_warehouse.workers`), `plan resolve-feed|workflow` (were repo-only scripts under `skills/bookkeeping/scripts/`), `doctor`, `skill install [--rules DIR]`. The rules folder is `EDGAR_RULES_ROOT`, else the checkout's, else the bundled copy. 2026-10-03 07:47 ET
- [x] G1: `tests/engine/test_data_skill_bundle_postgres.py` installs with the Setup's `uv tool install` command word for word from a git ref; no file in two wheels; every shipped module imports; no edgartools, spaCy, pandas, Streamlit or Snowflake connector; `doctor` ok on PG16 stores. Found and fixed: Clean MDM could not import without a rules folder. 2026-10-03 07:47 ET
- [x] G2: on an empty PG16 Rules Database, from the bundle: `skill install --rules`, `rules init`, `rules migrate`, `rules load`, `rules status`; the saved digest equals the loaded one. 2026-10-03 07:47 ET
- [x] G5: `doctor` follows subcommands at any depth and checks every flag; 63 command lines across the skills resolve; a skill naming `rules invent` is reported. First run found the walk too shallow (`change-journal recover bookkeeping --limit`), fixed. 2026-10-03 07:47 ET
- [x] The skill: `skills/data-platform/SKILL.md` (setup, the flow, parse, master marked not built until 20e, custom parsing, self-check), with `link.sh` and `agents/openai.yaml`; the four skills keep their detail and point to it; their commands are written as the installed `edgar-warehouse`. 2026-10-03 07:47 ET
- [x] 20e: MDM behind the protocol. `mdm.merge` (Merge Stage under an MDM run fixed by the effect key; receipt read back; `mdm.committed`), `mdm.publish` (one batch to one consumer in generation order; journal events under the run; `mdm.published`), every MDM transaction fenced by the live lease (`bookkeeping_guard`; the renewal keeps the proof current). The journal publisher no longer reads Bookkeeping's private state; `change-journal recover mdm` is gone. Rules: MDM targets name the workers and their checks; the invalid `mdm.publication` run check and `mdm.ingest` targets go; every target validates (the changed source versions need the operator's approval). `tests/integration/test_mdm_merge_worker_postgres.py` 3 passed: a Rules-submitted merge and publish to export, graph and the Change Journal with separate logins; a lost acknowledgement merges once and a forged receipt is refused; a lapsed lease commits nothing. Affected tests: 64 PostgreSQL passed; unit and architecture 215 passed, the 15 `jq` failures only. 2026-10-03 08:30 ET
- [x] `mdm.prepare`: a `source.read` reading into an MDM manifest, generic (table, dataset, policy, consumer, batch prefix and `as_of` are the unit's keys). 2026-10-03 08:30 ET
- [ ] Company read block, equivalence on the pinned capture, delete `company_source.py` and `loaders/`
- [ ] GLEIF read block, equivalence, delete `gleif_source.py`
- [ ] Person read block on the engine
- [ ] G4: custom-step mode, trialled on one real gap
- [x] G3: from the installed bundle, one Rules run reads captured records with the engine (`source.read`), prepares (`mdm.prepare`) and merges them into a real Clean MDM (`mdm.merge`), each step by a worker and a separate verifier (`test_parse_then_master_runs_through_the_installed_bundle`). 2026-10-03 08:30 ET
- [ ] G3 and the operator's "test it again from the beginning": the whole proof through the installed bundle on empty stores, compared with ticket 27 (6,414 Companies, 3,052 with CIK and LEI, second pass unchanged)
- [x] Decisions taken while building (no new question needed; each follows from the answers):
  - one command, `edgar-warehouse`, not a new `edgar-data`: every skill, test and habit already names it;
  - the four skills keep their detail and point to data-platform, rather than becoming one-line entries: data-platform is the one entry point, and each step's detail stays in one place (moving it would copy it);
  - the Bookkeeping specification and design and the Change Journal specification move into their skills (`SPEC.md`, `DESIGN.md`), so an installed copy has every document it links to. 2026-10-03 07:55 ET
- [x] Bundle PR, three-axis `/code-review`, findings fixed:
  - **GoF:** leave the structure; lift two mid-function imports (done); the plan commands and the worker arguments into their own modules (done, also a Standards point).
  - **Standards, fixed:** `skill install` stopped half-way on a refusal and could overwrite a changed copy (now checks all targets first, and keeps a digest of what it installed); the rules fallback could pick a stray `site-packages/rules` and let `mapdoc write`, `unload` and `approve --rule` write into the installed package (now the bundled copy wins and refuses writes, naming `EDGAR_RULES_ROOT`); `doctor` crashed on a malformed address and had no timeout; a pipe ends a command; one doc pointed at a deleted script.
  - **Spec, fixed:** `doctor` now checks written choices (`workers work|verify`), nested flags, checkout-only spellings and every relative link; G2 saves through the bundle; the parse run reads the copied rules folder; the installed console script itself runs `doctor`.
  - **Noted, not done:** `doctor` reads argparse internals (`_actions`); `NOT_BUILT` lists the two unbuilt rules commands in code.
- [ ] Bundle PR: CI green; merge on the operator's word
- [ ] Three-axis `/code-review` for each later PR; CI green; merge on the operator's word
- [ ] Memory `project_rules_skill.md` updated
