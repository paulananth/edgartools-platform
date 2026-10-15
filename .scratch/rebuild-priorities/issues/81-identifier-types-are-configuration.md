# Identifier types are configuration

Priority: 81, tier 2, the recreation proof. Map: [Rebuild priorities](../map.md).

Type: task (build). Status: open. Blocks: 79 (Onboard funds and securities with the skills).

## Why

Operator, 2026-10-14, on learning that MDM refuses an Identifier Contract whose normalizer it does not know: "why and why it takes so long, data profiling is not enough". Then "yes" to making identifier types configuration.

Root cause: every identifier type (CIK, LEI, CRD, and the new CUSIP and ISIN) is hand-written Python in two places, the formats a Dataset Contract checks values with (`adapters.FORMATS`) and the normalizers matching compares with (`primitives.NORMALIZERS`). Profiling already finds an identifier's shape and check-digit family, but nothing can take that finding as input, so each new identifier stops onboarding for a code change.

## What changes

- An identifier type is declared once, in `rules/identifiers/<name>.yaml`: its pattern, its case, the values refused as stand-ins, and its check-digit family, named as data-profiling names it.
- The engine implements each check-digit family once. Profiling's families and the engine's share their names, so a finding becomes a declaration with no translation.
- Each declared type gives a format (`<name>`, refusing with `invalid_<name>` or `invalid_<name>_checksum`) and a matching normalizer (`normalize_identifier@<name>-v<version>`), so an Identifier Contract can name it.
- CUSIP and ISIN are the first two declared types. They replace the hand-written versions on the unmerged branch `claude/security-id-formats`, whose tests carry over.
- CIK, LEI and CRD stay hand-written for now: their normalizers are pinned by approved Identifier Contracts (each a verified corpus hash), and changing their output would void those approvals.

## Checklist

- [ ] GoF consult before code
- [ ] The declaration format and its loader (`edgar_warehouse.rules.files`)
- [ ] Check-digit families in the engine, named as profiling names them; a test that the engine and profiling agree on each family
- [ ] Declared types feed `FORMATS` and `NORMALIZERS`
- [ ] `rules/identifiers/cusip.yaml` and `isin.yaml`; the CUSIP and ISIN tests carried over from `claude/security-id-formats`
- [ ] An Identifier Contract naming `normalize_identifier@cusip-v1` passes activation's check
- [ ] data-onboarding REFERENCE.md and data-profiling: how a finding becomes a declared type
- [ ] Out-of-date docs fixed: `docs/specs/source-contract/spec.md` (formats list), `docs/research/custom-parsing-inventory-2026-10-02.md`
- [ ] Affected tests pass locally
- [ ] Three-axis /code-review (Standards, Spec, GoF)
- [ ] PR, CI green, merge on the operator's word
- [ ] Close `claude/security-id-formats` unmerged, replaced by this ticket
- [ ] Learning → skill
