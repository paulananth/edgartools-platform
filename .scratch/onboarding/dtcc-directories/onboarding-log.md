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
- Skills/data-profiling is Claude-owned; do not change its reader during concurrent profiling work. Any refinement here is generic data-onboarding guidance on raw-format provenance and evidence status, after a clean overlap guard.
- No existing DTCC rules found under rules/sources. Source codes, part classifications, keys and identity joins remain undecided pending measured findings.
- Installed edgar-warehouse command is not on PATH. Do not reinstall the bundle or start stores for discovery; profile_data.py is the documented standalone command.

## Execution

Commands, capture receipts, measured results and questions will be recorded below.
