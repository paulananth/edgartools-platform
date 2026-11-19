# No load starts until the infrastructure is ready and tested

Status: open
Type: task

Operator: "donot start the load until the infrastructure is ready and tested that is how it is done in enterprise code it in skill".
A load was started right after init, before any gate existed, then stopped; its partial writes ran for about two minutes.

## Parts

- [x] Stop the load that was started too early; no process and no loader session remained (2026-11-19 07:17 ET)
- [x] `skills/data-operations/scripts/readiness.py`: nine checks (code committed, containing main, commit with green CI; engine built from this source; `doctor`; loader guards; reference data; captures; quiet instance; room; access audit) and `readiness.json` written only on a full pass for one store generation, one commit and one day (tests/unit/test_readiness.py: 33 passed)
- [x] `load_chain.py` refuses to start, resume or finish without the gate; `--plan`, `--list`, `--status`, `--catalog-status` stay read-only (tests/unit/test_load_chain.py: 147 passed with the readiness tests)
- [x] Run live: NOT READY on the first run for the right reasons (uncommitted code, CI not green, engine not recorded as built, audit skill not on the branch) (2026-11-19 07:17 ET)
- [ ] Merge, build the engine with `readiness.py --build-engine`, and re-run on `main` until it prints READY
- [ ] A rehearsal of the first lane on a disposable store as a tenth check
- [x] Learning → skill: `skills/data-operations/HOSTED-LOADS.md` holds the gate, its checks and how it closes; runbook step 9
