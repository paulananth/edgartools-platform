# Grok takeover: drop-identity-glue-edges

Scope: preserve the authorized Grok work, verify it, and check it in on `codex/drop-identity-glue-edges`. No deployment, matching-rule activation, database cleanup, or merge is included.

Recovery: original Grok worktrees are untouched. Heads, tracked patch and non-build untracked files are backed up at `~/.local/share/edgartools/branch-recovery/grok-takeover-20260926T171709Z/` with SHA-256 file manifest and Git bundle. Rust `target/` artifacts remain in the original worktree and are excluded from check-in.

- [x] Capture the source branch and unfinished files — bundle, patch and file manifest verified (2026-09-26 13:18 ET).
- [x] Transfer into a dedicated Codex branch/worktree based on `origin/main` `082d9461` — branch and status verified (2026-09-26 13:18 ET).
- [x] Review source/history with GoF — retain current dispatch design; fix stale type counts and names; record existing-store retirement limits below (2026-09-26 13:26 ET).
- [x] Verify — six affected MDM suites: 210 passed, zero skips; both shell scripts pass `bash -n` (2026-09-26 13:26 ET).
- [x] Review change scope — original 14-file removal plus narrow naming/comment fixes and this note; no generated artifacts or credentials; `git diff --check` passes (2026-09-26 13:26 ET).
- [ ] Commit and push the Codex branch, then verify the remote hash and clean worktree.

## Review

GoF review read the pipeline/graph implementation and its recent relationship-closing, batch and versioning history. Removing two fixed dispatch branches does not justify a new Strategy hierarchy. Existing explicit dispatch stays in place.

This change stops future derivation of `IS_ENTITY_OF` / `IS_PERSON_OF`, removes them from fresh registry seeds and CLI allowlists, and stops generating their named graph views. It does **not** delete/deactivate old registry rows, existing relationships or already-created Snowflake views. Default graph generation still reads active registry types on populated stores; old active glue rows can therefore remain in generic graph outputs. Full existing-store retirement needs a bounded, recoverable migration and downstream cleanup proof before anyone claims deployed removal. No live cleanup or rollout was performed.


## Verification

```bash
uv run --extra mdm --extra s3 pytest tests/mdm/test_cli_snowflake_graph.py tests/mdm/test_graph_generation_builder.py tests/mdm/test_pipeline_relationships.py tests/mdm/test_relationship_closing_pattern_registry.py tests/mdm/test_relationship_coverage.py tests/mdm/test_snowflake_graph_migration.py -q
bash -n scripts/ops/full-universe-sync.sh scripts/ops/sync-relationships.sh
```

Final targeted run: **210 passed** in 70.16 s, zero skips; 119 existing `datetime.utcnow()` deprecation warnings. An earlier cold-start run was interrupted and is not acceptance evidence. These suites use their existing SQLite/fake-executor harnesses; they do not prove an existing PostgreSQL/Snowflake migration or deployed graph cleanup.
