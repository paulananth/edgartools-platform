# MDM is just MDM: the words

Status: in review (2026-10-13 ET), branch `claude/mdm-naming`
Blocked by: none

The operator, 2026-10-13: "Purge Clean from MDM it's just MDM update readme". Scope chosen: "Words now, code next (Recommended)".

- [x] GoF consult: wording only, nothing structural; the catalog's `CLEAN` schema constant goes with ticket 27 (2026-10-13 17:53 ET)
- [x] "Clean MDM" becomes "MDM" in 55 living files: README, CONTEXT.md, CLAUDE.md, AGENTS.md, the skills, docs/specs, code docstrings, comments, CLI help and one error message, the infra scripts' comments and stage descriptions, test docstrings; a grep of those finds 0 left (2026-10-13 17:53 ET)
- [x] `docs/specs/clean-mdm/` moved into `docs/specs/mdm/` (no name clashes); 88 files' links updated, ticket history included (2026-10-13 17:53 ET)
- [x] CONTEXT.md: "There is one MDM. It is not called Clean MDM" (2026-10-13 17:53 ET)
- [x] Left as written, on purpose: `rules/**` (its bytes make the approved rules digest), `edgar_warehouse/mdm/migrations/001_mdm.sql` (an applied migration), `crates/source-contract/**` (a Codex path; one comment still names the old spec path), the replayed rulings in `.scratch/profiling/trials/proof/rulings.jsonl`, docs/adr and docs/research (records), and ticket prose under .scratch and .planning (2026-10-13 17:53 ET)
- [x] Affected tests: the CLI, architecture, rules digest, survivorship and catalog tests; 380 pass, and the 17 failures (secrets manifest, dbt secret, install wizard preflight) fail the same way on main without this change (2026-10-13 17:53 ET)
- [ ] PR, CI green, merge on the operator's word
