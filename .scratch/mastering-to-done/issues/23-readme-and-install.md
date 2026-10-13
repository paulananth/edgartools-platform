# 23: README and install.sh match the platform as it is

Status: in progress (Claude, branch `claude/readme-install-refresh`). Raised by the operator, 2026-10-13: "Update readme of the repo and update install.sh and other step functions"; scope, 2026-10-13: "README + install.sh now (Recommended)" (Step Functions: ticket 24).

## Checklist

- [x] Found (2026-10-13 17:26 ET): no Step Functions definition is left on main (no `StartAt`, no `aws_sfn_state_machine`); the old pipeline's were retired with its commands (#766, platform validation 2b). install.sh created none of the configured platform's stores (Rules, Bookkeeping, Change Journal, RDM, silver), and named files and paths that are gone (`silver_store.py`, `mdm/export.py`'s exporter, `one_click_data_refresh`, gold-refresh stages, ECS task definitions in the deploy phase)
- [x] install.sh: a stores phase, each store created (`init`, which changes nothing when rerun) and upgraded (`migrate`) for its runtime login, named by `INSTALL_*_ROLE` (defaults are placeholders); the MDM stage passes its application login and installs Bookkeeping's destination guard (`bookkeeping init-guard`); a last `doctor` stage; no store address on any command line; stale descriptions corrected; the ECR cleanup note says no task definition may be active now, so cleanup would protect no digest. GoF consult: leave the structure (one `add_stage` per store, the script's own pattern). Tests: the stage order and a stores test, `test_install_wizard.py` and `test_install_redact_text.py` 47 passed; `bash -n` passes; shellcheck runs in CI (2026-10-13 17:26 ET)
- [x] README: publication as change data capture and force publish; the engine's formats (Parquet, the SGML container); a Sources table; Install points at install.sh and its stores, and says the worker runtime on AWS is not in the plan yet (ticket 24) (2026-10-13 17:26 ET)
- [ ] Three-axis review, findings fixed
- [ ] PR, CI, merge on the operator's word
