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
- [ ] Ownership change written where Codex reads it (the implementation notes and the 13F workstream ticket)
- [ ] Packaging facts: the engine wheel needs Rust and maturin to build from a git ref; does `../../` force-include survive a `git+…#subdirectory=` install
- [ ] GoF consult on the entry point and the package layout
- [ ] Bundle skeleton: `packages/data-skill` (`edgartools-data`, command `edgar-data`): one entry point registering the existing `rules`, `bookkeeping`, `change-journal`, `mdm` and worker commands, plus `doctor`
- [ ] G1 test: install from a git ref in a clean environment; `doctor` passes
- [ ] G2 test: rules init, migrate, load, save and status from the installed bundle
- [ ] G5 test: every command a skill names resolves
- [ ] The skill: `skills/data-platform/SKILL.md` orchestrates (setup, onboard, refine, parse, master, custom step, recover, self-check); the four old skills become thin entries
- [ ] 20e: the MDM worker and verifier behind the protocol
- [ ] Company read block, equivalence on the pinned capture, delete `company_source.py` and `loaders/`
- [ ] GLEIF read block, equivalence, delete `gleif_source.py`
- [ ] Person read block on the engine
- [ ] G4: custom-step mode, trialled on one real gap
- [ ] G3 and the operator's "test it again from the beginning": the whole proof through the installed bundle on empty stores, compared with ticket 27 (6,414 Companies, 3,052 with CIK and LEI, second pass unchanged)
- [ ] Three-axis `/code-review` per PR; CI green; merge on the operator's word
- [ ] Memory `project_rules_skill.md` updated
