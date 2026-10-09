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
