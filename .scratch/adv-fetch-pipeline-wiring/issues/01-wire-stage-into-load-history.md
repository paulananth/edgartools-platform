# 01 — Wire the new AdvBulkFetch Stage into `load_history`

**What to build:** In `load_history`'s generated Step Functions definition
(`write_load_history_definition` in `infra/scripts/deploy-aws-application.sh`), insert a
new sequential Stage — a `FetchAdvBulk` Task followed by an `IngestAdvBulkSources` Task —
after `Stage1BThirteenF` (the last bronze/silver step) and before `MdmRun`, so ADV
adviser/fund silver data is always current before MDM entity resolution runs. `FetchAdvBulk`
must branch on the optional `$.force` SM-input field (a bare boolean CLI flag, so this needs
Choice-based branching between two literal command shapes, not `States.Format`
interpolation) and default `$.dataset_period` to an empty string when absent (mirroring
`ArtifactPolicyCheck`/`ArtifactPolicyDefault`'s existing Check→Default pattern).
`IngestAdvBulkSources`'s `--source-manifest` argument must resolve to the same
deterministic, run-id-scoped manifest path `FetchAdvBulk` writes to. Both new Task states
need a lenient `Catch` that falls through to `MdmRun` on failure, matching the existing
Branch B / AD-13 pattern — a transient ADV fetch/ingest failure must never abort the rest
of `load_history`.

**Blocked by:** None — can start immediately.

**Status:** ready-for-agent

- [x] The generated `load_history` JSON has a new stage running after
      `Stage1BThirteenF` and before `MdmRun`.
- [x] With no SM-input overrides, `FetchAdvBulk`'s command is
      `fetch-adv-bulk --dataset-period '' --run-id <execution-name>` (no `--force` token).
- [x] A `DatasetPeriodCheck`/`DatasetPeriodDefault` pair precedes the stage, injecting an
      empty-string default when `$.dataset_period` is absent — mirroring
      `ArtifactPolicyCheck`/`ArtifactPolicyDefault`.
- [x] A `ForceCheck` Choice state routes to two distinct `FetchAdvBulk` command shapes —
      one including the literal `--force` token, one omitting it — both converging on the
      same next state.
- [x] `IngestAdvBulkSources`'s `--source-manifest` argument is a `States.Format` expression
      resolving to the same manifest path convention `FetchAdvBulk` writes to (command
      name + run id), not a hardcoded or mismatched path.
- [x] A `Catch` on both `FetchAdvBulk` and `IngestAdvBulkSources` falls through to
      `MdmRun` on any error.
- [x] New structural tests in `tests/architecture/test_load_history_state_machine.py`
      (generated-JSON assertions, no AWS calls) cover all of the above, following the
      file's existing naming/assertion conventions.
- [x] All pre-existing tests in `test_load_history_state_machine.py` still pass.
