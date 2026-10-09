# DTCC directories onboarding investigation

Status: discover; findings unapproved. Owner: Codex.

Operator instructions:
- "keep Security Position Reports and Selected CUSIP restriction/certification lists in scope but lower priority now create a checklist of tasks"
- "can you check in create a pr and then start on priority 1"
- "can you use the data profiling, data onboarding skill to investigate insted of shooting from the hip, also refine the skills as needed"

Skills read: data-onboarding and data-profiling from this branch at main
1735dd43. Investigation uses existing profiling commands on local captures.
No approval, activation, store mutation or automatic Company binding.

## Decisions and gaps

- Working dataset label: DTCC public directories (investigation label, not an approved source code).
- Current data-profiling reader supports CSV/Parquet/JSON/XML/database inputs but not XLSX. Test raw workbook refusal before profiling derived copies.
- Workbook exports are investigative inputs; raw and derived hashes, sheet/header choices, source row coordinates and count checks must accompany findings. Production XLSX parsing remains unqualified.
- Skills/data-profiling is Claude-owned; do not change its reader during concurrent profiling work. Any refinement here is generic data-onboarding guidance on raw-format provenance and evidence status, with an explicit ownership decision if the guard reports overlap.
- No existing DTCC rules found under rules/sources. Source codes, part classifications, keys and identity joins remain undecided pending measured findings.
- Installed edgar-warehouse command is not on PATH. Do not reinstall the bundle or start stores for discovery; profile_data.py is the documented standalone command.

## Execution

Commands, capture receipts, measured results and questions will be recorded below.

- Operator ownership answer: "Authorize Codex to coordinate this skill edit". Foreign onboarding edits concern an identifier example only; the discover guidance is disjoint. All profiling-code paths remain untouched.
- Standalone profile command: `uv run --with duckdb --with pyyaml python profile_data.py run --name "DTCC public directories September–October 2026" --input <one argument per derived-manifest region> --out /private/tmp/dtcc-priority1-20261009/profile --kinds company`. Fourteen arguments, fourteen full regions; CLI exit 0, 14.9 seconds.
- Original XLSX probe: same run command with `--input dtc=<raw workbook>`; exit 1, unsupported format xlsx.
- Export verification: `uv run --no-project --with openpyxl python .scratch/onboarding/dtcc-directories/check_export.py`; four adversarial checks passed. Every real region's JSON cells roundtripped exactly.
- Genericity: `uv run --no-sync pytest -q tests/unit/test_profiling_genericity.py`; 58 passed.
- Generated profile has 22 unanswered questions and draft approval. Report title is None due to a reproduced parameter-shadowing bug; original output is kept unchanged.
- No operator findings approval recorded. Stop discover before plan-parts, map, test/activate or any MDM writes.

## Repeat discovery with narration (2026-10-09)

- Operator: "merge and redo the reserch of indentified dtcc source reserch using the updated skills".
- PR #893 merged as `4489170c` after all six CI checks passed. A new isolated
  `codex/dtcc-discovery-repeat-20261009` branch starts at that main tip.
- Read the updated data-profiling and data-onboarding narration instructions.
  Explained access/cadence, reader limitations, duplicates, worksheet boundaries
  and rights findings in live conversation during investigation.
- Reverified official sources via the research skill. Its background agent
  wrote the cited official-source note; Codex independently verified the full
  licence clauses from the same HTML hash. No foreign worktree or skill edit.
- Ten bounded anonymous recaptures: HTTP 200, all prior hashes identical,
  5.59 seconds. All prior derived and grid hashes verified. Downloads completed
  before the full restrictions were discovered. No recurring acquisition set up.
- Repeated the documented `profile_data.py run` with the same fourteen local
  inputs and `--kinds company`: full scan, exit 0, 21.2 seconds command time,
  9.2 seconds profiler time. Parts/questions identical; fingerprints byte-identical.
  Exact arguments and hashes: `repeat-20261009/profile-command.json` and
  `repeat-20261009/qualification.json`. Same snapshot cannot prove key persistence.
- Repeated original XLSX probe: exit 1 with `found ['xlsx']`. All fourteen
  regions compared cell-for-cell with original sheets; no export correction,
  row dropping, deduplication or production parser added.
- Inspected every draft question: nine unknown classes, nine designed keys,
  four proposed master kinds. Recommendations remain algorithm suggestions.
  Boundary and role review is needed before approving any of them.
- DTC numerical sheet: 914 account-shaped rows, 73 series headings, 3 blanks;
  account representations match the alphabetical list. Names agree only after
  trimming; that diagnostic comparison is not an approved normalization rule.
- NSCC duplicate key: original rows 3000/3001 are identical across all columns.
  Corporate MPID pairs at 898/899 and 921/922 differ in clearing broker only.
  Evidence saved in `repeat-20261009/local-evidence.json`.
- Full DTCC terms restrict database compilation and automated extraction except
  with applicable authorization. Rights are an unresolved onboarding boundary.
  No external permission request, purchase or registration performed.
- Final research: `docs/research/dtcc-discovery-repeat-2026-10-09.md`.
  Findings remain unapproved. No `plan-parts`, mapping, activation or MDM writes.
