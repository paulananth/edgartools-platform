# A reset store inherited the old chain's done steps

Status: open
Type: bug

## Parts

- [x] Root cause: the chain's state file had a marker with no generation (written before generations were recorded), and `state_verdict` trusted it when the database generation was readable; the reset store therefore counted 59 old steps as done and the scheduler ended at once. 2026-11-19 11:36 ET
- [x] Fix: a marker with no generation is trusted only while the generation cannot be read now; a blip at creation is written explicitly as `generation ?` and learns the generation later; `tests/unit/test_load_chain.py` (two new tests failed before the fix: `state_verdict` returned "same" for a legacy marker). 2026-11-19 11:36 ET
- [x] The live file was set aside by hand (`chain-fresh-v1.log.reset-2026-11-19-stale-marker`) and the scheduler restarted: it started `nport-security`. 2026-11-19 11:36 ET
- [ ] Merge the PR when CI is green
- [x] Learning → skill: data-operations `HOSTED-LOADS.md` (a chain that ends at once after a reset). 2026-11-19 11:36 ET
