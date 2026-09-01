# 01 — Rename the MDM Pipeline Stage Names

Type: task
Status: open

## Question

Rename the four MDM-stage names in the Step Functions state machines from
their current internal/technical labels to business-readable ones (decided
by the operator, not open for re-litigation):

| Current | New |
|---|---|
| `MdmRun` | `Mastering` |
| `MdmExport` | `Publish` |
| `MdmSync` | `Publish Relationships` |
| `MdmVerify` | `Reconcile` |

Motivation: these names are what shows up in the Step Functions console,
execution history, and CloudWatch — the actual surface an operator (or a
non-technical stakeholder walked through an execution) sees. `MdmRun`/
`MdmExport`/`MdmSync`/`MdmVerify` read as internal command names, not as
what each stage actually does. See CLAUDE.md's "Phased Pipeline" section
for the current names and what each stage does.

## Confirmed scope: Step Functions state names

Grepped `infra/scripts/deploy-aws-application.sh` — these four strings
appear **36 times**, as literal Step Functions state keys (`"MdmRun":
mdm_run`, `next_state="MdmExport"`, etc.) across at least the
`daily_incremental`/`bootstrap` state-machine-writer function and the
`load_history` one (confirmed via multiple independent `next_state="MdmRun"`
call sites and a `SeedUniverse`-adjacent reference, which is `load_history`'s
own Stage 0 predecessor per CLAUDE.md). Renaming means:

- Updating every state-key string and every `next_state=`/`Next=` reference
  pointing at these four names, in every state-machine-writer function that
  defines them (not just one) — a plain find-and-replace across the literal
  strings should be safe *if* it's applied consistently everywhere, but
  each writer function should be re-read in full first in case any embeds
  the name in a comment or log message that also needs updating for
  consistency, not just the JSON state keys.
- Re-running `deploy-aws-application.sh` against every environment (today:
  prod only, per CLAUDE.md's dev-decommission note) to actually apply the
  renamed state machine definitions — a definition change with no redeploy
  is a no-op.
- Confirming no in-flight execution is running against the old state names
  at deploy time (a rename mid-execution would break `Next` resolution for
  that execution) — check via `list-executions --status-filter RUNNING`
  before deploying.
- CLAUDE.md's own "Phased Pipeline" section (and any other doc referencing
  these names) needs updating to match, or it goes stale immediately.

## Open scope question — not yet decided, flag before implementing

Does this rename extend to the underlying **CLI subcommands** (`mdm run`,
`mdm export`, `mdm sync-graph`, `mdm verify-graph` in
`edgar_warehouse/mdm/cli.py`) and their Step-Functions-invoked ECS task
definitions/log-stream prefixes (`mdm-mdm-small`, `mdm-mdm-large`), or is
this rename scoped to the state-machine **display names only**, with the
CLI commands themselves (and everything that invokes them — runbooks,
`bootstrap-prod-mdm.sh`, ad-hoc operator commands, this session's own
established `aws stepfunctions start-execution` patterns) staying as they
are?

Renaming the CLI commands is a much larger blast radius — it breaks any
existing runbook/muscle-memory command, any external script invoking
`mdm run`/`mdm export`/etc. directly, and touches `edgar_warehouse/mdm/
cli.py`'s argument parser, not just the state machine JSON. The state names
alone accomplish the stated goal (a readable execution history/console
view); the CLI rename does not appear to be required for that goal and
should not be assumed in scope without asking first.

**Recommendation for whoever picks this up: confirm with the operator
whether CLI commands are in scope before touching `edgar_warehouse/mdm/
cli.py` at all.** Default to state-machine-names-only if not explicitly
told otherwise.

## Also check before implementing

- `/gof-refactor-reviewer` per CLAUDE.md's hard rule, before editing
  `deploy-aws-application.sh` (a large, frequently-changed file).
- Whether any CloudWatch alarm, dashboard widget, or the operator-alert SNS
  topic (`sec-edgar-pipeline-alerts`) references these state names by
  string anywhere — a rename would silently break string-matched alerting
  if so.
- Full 3-axis code review (Standards/Spec/GoF) before commit, per CLAUDE.md.
