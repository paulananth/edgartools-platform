# Switch on GLEIF over the captured Golden Copy

Priority: 116 (operator, 2026-10-19: "Can you turn on company mastering one source at a time sec, geilf, and the rest"; GLEIF follows SEC Company, ticket 114). Map: [Rebuild priorities](../map.md).

Type: task. Status: done (#1112 merged 2026-10-19 12:55 ET). Blocked by: none.

## Found (2026-10-19 ET)

- GLEIF's only target, `mdm`, merged records prepared elsewhere (the 2026-10-14 installed proof built its units by hand), so no platform command ran GLEIF over a capture.
- Its reading takes two inputs from outside the Golden Copy: the approved scope of LEIs (a contract reference) and the publication's record count (context), plus the N-PORT issuer LEIs (a lookup set). The declared writer had no way to take a run's own inputs.
- GLEIF declared no `acquisition`, which a source that masters needs to register its datasets.

## Checklist

- [x] The declared form takes a run's own inputs (generic, approved 2026-10-19 "Yes, both generic"): a target's `run: {facts, files}`; a context value `{fact: <name>}`; a lookup set or a contract reference `{file: <name>}`; `rules test` and `mdm prepare-capture` take `--fact name=value` and `--file name=path`; each file's digest joins the processing identity and the run's ids. GoF consult: three small data-driven branches in `read_units.form`, no new structure. Tests: `tests/mdm/test_read_units.py` (4 new, 17 passed). Bookkeeping SPEC says so
- [x] GLEIF configuration: `acquisition` declared (the Golden Copy feed; declaring it sends no request), `execution.max_artifacts: 1`, a version-2 `mastering` target (Level 1 read, prepare, merge, processed), the unused `mdm` target removed (its name made the sandbox require an approval); `rules/source-sequence.yaml` names `mastering`
- [x] A capture folder for the 2026-09-11 Golden Copy (links to the research copies, no copy; `receipts.jsonl` with each file's sha256) and the run files: the 3,755 approved LEIs of the 2026-10-14 proof, an empty N-PORT issuer list
- [x] `rules test --source gleif --target mastering`, two passes on a fresh store (2026-10-19 12:28 ET; 21 min 32 s): passed, the second pass changed nothing; GLEIF alone stages 3,716 Level 1 records waiting to bind to a Company (`binding_required`) and sets aside 39 (`unsupported_identity_kind`), the GLEIF counts of the 2026-10-14 proof; affected tests 1,928 passed (the catalog's lineage test now names GLEIF's feed)
- [x] Saved as `gleif-2026-10-19.pipes-on`, its test run recorded as its proof (the report's digest equals the saved version's), approved under the standing approval, active in the `company-on` store after Company; `rules run` (no feed) over the Golden Copy (2026-10-19 12:45 ET): complete in 12 min (read 11 min), every step verified; 225 of the 3,716 Level 1 records bound to the 486 Companies mastered there (711 bind decisions with Company's), 3,491 wait to bind (their Companies are outside the 512-document bundle), 39 set aside; no identifier on two masters
- [x] Three-axis review (2026-10-19 12:31 ET): GoF: leave it (the step-input refusal message now names `references`). Spec: the data-onboarding and data-operations skills now give `--fact`/`--file` for `rules test`, `mdm prepare-capture` and the run; the test report records the run's facts and each file's sha256 (`run_inputs`). Standards: a fact now joins the processing identity (a corrected count reprocesses); a run's facts and files are checked when the manifest is written, not at a worker: a reference must be one the contract declares empty and the filled contract within 1 MiB; a lookup set file matches the contract's sets (names, list or pair shape, count, 64 MiB); an unreadable or non-JSON file and a fact of another type are refused by name. Tests: `tests/mdm/test_read_units.py` 21 passed (4 more)
- [x] PR, CI, merge: #1112 merged 2026-10-19 12:55 ET (checked 2026-10-21 21:02 ET)
- [x] Learning → skill: #1112, a run's facts and files (`skills/bookkeeping/SPEC.md`, `skills/data-onboarding/SKILL.md`, `skills/data-operations/SKILL.md`) (checked 2026-10-21 21:02 ET)

## Answer

GLEIF runs from a captured Golden Copy, with a run's facts and files. Merged in #1112 (2026-10-19 12:55 ET).
