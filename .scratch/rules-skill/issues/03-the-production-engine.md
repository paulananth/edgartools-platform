# The production engine

Type: task
Status: moved to `mastering-to-done/issues/08-configured-parsing-engine.md`; Codex's research (#784) recommends keeping per-source readers (2026-10-02 audit, mastering to-do 01).
Was: open
Blocked by: 01

## Outcome

`edgar_warehouse/rules/engine.py`, ported from the prototype
(`.scratch/source-contract/prototype/engine/source_engine.py`) with only what
the commands need. The new shape: `read` produces rows, `mdm` maps those rows
through `adapters.normalize`, and `silver` gives types and keys. Adds
`rules check <source>`.

## Checklist (times ET)

- [ ] `/gof-refactor-reviewer` before code.
- [ ] Readers (json, jsonl, xml, csv, zip), primitives, the `custom.py` API,
  checks, fixture tests and the batch gate.
- [ ] The prototype's gleif, form345 and codex-fixture sources pass as test
  fixtures; the import-boundary tests stay green; no sockets are opened.
- [ ] Amend ADR 0016 (parse each run) and the Source Contract spec (`mdm`
  maps from `read` rows).
- [ ] Three-axis `/code-review`, then PR and CI.
