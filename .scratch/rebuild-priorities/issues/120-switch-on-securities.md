# 120: Switch on Securities over captured files

Priority: 120 (operator, 2026-10-19: "Can you turn on securities"). Map: [Rebuild priorities](../map.md).

Type: task. Status: in progress (Claude, 2026-10-19). Blocked by: none.

## Found (2026-10-19 13:58 ET)

- Everything Securities need is captured locally: the 2026 Q2 N-PORT data set
  (one zip) and OpenFIGI's answers for its CUSIPs (7,674 files) and ISINs
  (7,754 files, each answer with its request). No provider request.
- `sec.nport.security` declares no run target; its chain was proved only by
  hand-chained scripts (`.scratch/onboarding/sec.nport/security_*.py`).
- The gap: its combine attaches an ISIN to a CUSIP only when OpenFIGI agrees
  (`figi-*.yaml`, operator 2026-10-15: "Use FIGI to add pairs too"), so it
  reads OpenFIGI's answers. A run reads one capture, and a step reads only
  its own run's steps, so no configuration reaches them.
- Ruling (operator, 2026-10-19, asked how to close it): "Read another run
  (Recommended)": a generic change, a step may read the verified output of
  another finished run, named in configuration.

## Design

- A combine's reading may name another source's target and step:
  `{run: {source: <source>, target: <target>, step: <step>}}`. When the
  manifest is written, every verified unit of that step in the complete runs
  of that target (the latest run's unit for a key held by several) becomes
  the slot's list, each `{run, step, key}`; their receipts join the run's
  identity.
- Bookkeeping fills such a slot the way it fills its own: the other run's
  unit must be verified, its chain is reverified against that run's frozen
  configuration, and only its receipt is handed on.
- OpenFIGI gains one target per kind that reads its answers the way the
  Securities chain needs them (`sec.nport.security/figi-requests.yaml` and
  `figi-answers.yaml`, cross-source contracts); Securities' `mastering`
  target reads those runs. The sequence runs those OpenFIGI targets before
  Securities.

## Checklist

- [x] GoF consult on Bookkeeping's slot filling and the target manifest (2026-10-19 17:56 ET): leave it; `_dependency` (config) and `_receipt` (engine) each gain one case, unchanged since #928
- [x] A slot names another run's unit; Bookkeeping fills it only from that run's verified unit, reverified against that run's own frozen configuration; the fill cache keys the run too (2026-10-19 17:56 ET). Tests (`test_configured_bookkeeping_postgres.py`): read; unknown run, not verified, corrupt receipt each block without execution; a malformed run id refused
- [x] A combine's reading, or a read's lookup set, may name `{run: {source, target, step}}`: the manifest writer lists the verified units of that target's complete runs (`Bookkeeping.verified_units`: an output held twice, the same files read again, listed once; group keys repeat across runs, so never "latest per key"), and their outputs join the processing identity (2026-10-19 17:56 ET). Tests: `tests/mdm/test_target_manifest.py` (slots, identity moves, 0 and 257 refused, a lookup read whole, bad selectors refused), the Postgres listing test
- [x] A target that only reads (no `mdm.prepare`), for another run to read; two preparations refused (2026-10-19 17:56 ET); tests in `test_target_manifest.py`
- [x] `rules test` finds another run in its own stores' Bookkeeping, not the shell's (2026-10-19 17:56 ET)
- [ ] OpenFIGI targets that read the answers for Securities (CUSIP, ISIN)
- [ ] Securities' `mastering` target, declared from the hand-chained runs
- [ ] `rules/source-sequence.yaml`: OpenFIGI's answer targets, then Securities
- [ ] `rules test` on Securities, recorded; approval under the standing approval; activation in `company-on`
- [ ] Runs in `company-on`: OpenFIGI's answers (CUSIP, ISIN), then Securities; counts; no identifier on two masters
- [ ] Three-axis review; PR, CI, merge
- [ ] Learning → skill
