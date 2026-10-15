# Identifier types are configuration

Priority: 81, tier 2, the recreation proof. Map: [Rebuild priorities](../map.md).

Type: task (build). Status: open. Blocks: 79 (Onboard funds and securities with the skills).

## Why

Operator, 2026-10-14, on learning that MDM refuses an Identifier Contract whose normalizer it does not know: "why and why it takes so long, data profiling is not enough". Then "yes" to making identifier types configuration.

Root cause: every identifier type (CIK, LEI, CRD, and the new CUSIP and ISIN) is hand-written Python in two places, the formats a Dataset Contract checks values with (`adapters.FORMATS`) and the normalizers matching compares with (`primitives.NORMALIZERS`). Profiling already finds an identifier's shape and check-digit family, but nothing can take that finding as input, so each new identifier stops onboarding for a code change.

## What changes

- An identifier type is declared once, in `rules/identifiers/<name>.yaml`: its parts (each a length and the characters it may hold), its case, the values refused as stand-ins, and its check-digit family, named as data-profiling names it.
- The engine implements each check-digit family once. Profiling's families and the engine's share their names, so a finding becomes a declaration with no translation.
- Each declared type gives a format (`<name>`, refusing with `invalid_<name>` or `invalid_<name>_checksum`) and a matching normalizer (`normalize_identifier@<name>-v<version>`), so an Identifier Contract can name it.
- CUSIP and ISIN are the first two declared types. They replace the hand-written versions on the unmerged branch `claude/security-id-formats`, whose tests carry over.
- CIK, LEI and CRD stay hand-written for now: their normalizers are pinned by approved Identifier Contracts (each a verified corpus hash), and changing their output would void those approvals.

## Checklist

- [x] GoF consult before code: `FORMATS` grew five times along one axis (CIK, LEI, name id, CUSIP, ISIN) and each change also touched `NORMALIZERS`; table-driven declarations justified, CIK/LEI/CRD left in code. 2026-10-14 20:31 ET
- [x] The declaration format and its loader (`edgar_warehouse.rules.files`): parts, case, check digit, stand-ins; a family that cannot read the parts' characters is refused (review finding). Tests in `tests/mdm/test_clean_identifier_types.py`. 2026-10-14 20:31 ET
- [x] Check-digit families in the engine, named as profiling names them; a test that the engine and profiling agree on each family both hold (six on main; the two letter families join when `claude/profile-identifiers` merges). 2026-10-14 20:31 ET
- [x] Declared types feed `FORMATS` and `NORMALIZERS`; a declared name never replaces a hand-written one. 2026-10-14 20:31 ET
- [x] `rules/identifiers/cusip.yaml` and `isin.yaml`; the CUSIP and ISIN tests carried over from `claude/security-id-formats` pass (18). A test pins each version's digest. 2026-10-14 20:31 ET
- [x] An Identifier Contract naming `normalize_identifier@cusip-v1` passes activation's check (test). 2026-10-14 20:31 ET
- [x] data-onboarding REFERENCE.md and SKILL.md, and data-profiling: how a finding becomes a declared type; genericity lint passes. 2026-10-14 20:31 ET
- [x] Out-of-date docs fixed: `docs/specs/source-contract/spec.md` (formats list), `docs/research/custom-parsing-inventory-2026-10-02.md`. 2026-10-14 20:31 ET
- [x] Affected tests pass locally: testmon over tests/mdm, tests/unit, tests/architecture, 1,034 passed, and the install wizard's 34 with Python 3.12 first on PATH (6 min 27 s). The Rules Database export test (Postgres) runs in CI. 2026-10-14 20:31 ET
- [x] Three-axis /code-review (Standards, Spec, GoF). Fixed: a family that cannot read a character crashed the run (now refused at load); the Rules Database export left the types behind (now copied); a version could change in place (digest test); a list of stand-in values. Kept: the families are written in the engine and in profiling (a transient skill script the engine cannot import), held equal by test; types load once per process from `EDGAR_RULES_ROOT`. GoF: leave it. 2026-10-14 20:31 ET
- [x] PR #975, CI green, merged on the operator's word ("yes", merge `4da40b6a`). 2026-10-14 20:41 ET
- [x] Close `claude/security-id-formats` unmerged, replaced by this ticket: it had no PR; remote branch and worktree deleted. 2026-10-14 22:47 ET
- [x] Learning → skill: data-onboarding REFERENCE.md "Identifier types" (a new identifier is declared, never coded) and SKILL.md map step. 2026-10-14 20:31 ET
