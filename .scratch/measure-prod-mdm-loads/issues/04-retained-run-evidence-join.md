# Which retained runs can be verified, and how does the evidence join?

Type: research
Status: resolved
Blocked by:

## Question

The report needs one row per target with start/end ET, run IDs, and a verified/pending status. Two
independent retained sources describe the same runs: the private load logs under
`~/.local/share/edgartools/load-logs/` and the Bookkeeping run records in the control store, plus
bundle manifests under `~/.local/share/edgartools/hosted-prod/manifests/load/<source>/<target>/`.
What is the join, and which runs verify?

Establish, for each of the 13 sequence sources and the additional ordered targets:

1. The retained load-log candidates: file name, the source/target it names, the run IDs it mentions,
   the start/end markers or `Done:` summary it contains, and any `time -p` output. Modification time
   is a search hint only, never evidence.
2. The Bookkeeping run records: which run IDs exist, their status, expected vs verified units, and
   pending deliveries. Do not connect to the production MDM/Postgres endpoint; the control-store
   evidence is the retained snapshot under the private load-logs directory (the
   `measure-prod-fast-20261112-141251-ET` snapshot) unless a safe local read shows otherwise.
3. The bundle manifests: what each manifest contributes (capture run, receipts, publication
   metadata, considered/selected/already-processed/loaded counts).
4. The join key between a log, a Bookkeeping run and a manifest, and the precedence rule when they
   disagree.
5. Which runs meet the acceptance bar: status `complete`, expected units equal verified units,
   `pending_deliveries` zero. Note explicitly which are historical-only because the current store
   does not know the run ID.

Write the findings to `.scratch/measure-prod-mdm-loads/evidence/04-retained-run-evidence-join.md`.
No credentials, DSNs, host values, source row values or record identifiers.

## Answer

Evidence: [04-retained-run-evidence-join.md](../evidence/04-retained-run-evidence-join.md)
(branch `codex/wayfinder-measure-prod-loads-20261113`, commit `7758ed5b`).

- **The Bookkeeping run export (391 runs, 358 complete / 33 running) is the only source of run
  state.** Nine targets meet the acceptance bar; six are partial; `sec.ownership/security_symbols`
  is blocked (zero runs); `sec.nport.security/mastering_other_keys` has no export rows at all.
- **The load-log summaries join to the export on `run_id`**, for 16 of 32 invocations; the other 16
  (`golive-*`, `small-golive-*`) are historical-only. All 32 reconcile
  `considered = new + already`.
- **The private manifest tree does not join to the export.** Run-id overlap is **zero** and all
  391 export `inputs_uri` manifest paths are gone from disk: the manifest tree was rebuilt after
  the export was taken and holds a **later wave** of runs (2026-11-12 22:32 UTC → 2026-11-13 15:07
  UTC) on the same targets. It supplies per-step receipts and document counts but **no verification
  state**, so it cannot upgrade a `partial` row to `complete`.
- **Precedence rule:** the export's run state wins over the log narrative for state, units and
  pending; the log's counts stand alone; the manifest tree never overrides the export.
- **No retained log contains `time -p` output** and no invocation start/end timestamp survives, so
  `active_command_seconds` and `target_wall_seconds` are unavailable for every target; only the
  run span and the step intervals exist.
