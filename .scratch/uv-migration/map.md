# Migrate to full uv for all usage and usecases

Type: wayfinder:map

## Destination

A migration plan (spec, not execution — this map produces the plan; carrying
it out is separate, later work) that brings every `pip install`/bare `dbt`
call site in this repo's *own internal automation* into compliance with the
already-established uv convention (`uv sync`/`uv pip` for installs, `uv run`
for anything with project dependencies or transient tools like
`dbt-snowflake`/`snowflake-cli-labs`), while explicitly leaving alone
call sites that don't need or benefit from it.

## Notes

- Ground truth for "compliant" is CLAUDE.md's existing uv section: "always
  use `uv` for Python dependency management and Python CLI execution... never
  invoke bare `pip` or bare `dbt`... use `uv run --with <package>` when a
  deploy needs a transient tool such as `dbt-snowflake`."
- **Measured fact (2026-08-04):** `uv run` has real per-invocation overhead —
  ~537ms vs ~88ms for plain `python3` on a trivial stdlib-only call (10-run
  average, this environment). Not a rounding error: `deploy-aws-application.sh`
  alone has 15+ standalone `python3 - <<PY` heredoc calls that import only
  `json`/`sys`/`pathlib` — wrapping all of them in `uv run` would add
  roughly 7-10s of pure sync-check overhead per deploy run for zero benefit.
  Every ticket on this map must weigh this, not treat "more uv" as free.
- **Confirmed fact:** `dbt-snowflake` and `snowflake-cli-labs` are not in
  `pyproject.toml` (no core dep, no extra) — deliberately transient tools.
  `uv run --with dbt-snowflake dbt ...` is the correct pattern; there's no
  live convention yet for `snowflake-cli-labs` (used across multiple steps
  in `smoke-test.yml`, not a single one-off call — `uv run --with` per-step
  may not fit as well as it does for a single `dbt` invocation).
- Use `/grilling` + `/domain-modeling` for decision tickets, per this
  effort's default. Use `/research` subagents for research tickets.

## Decisions so far

- [Destination shape](.) — plan/spec only, not full execution; this map's
  tickets decide, later work executes.
- [Dockerfile ENTRYPOINT scope](.) — out of scope. Runtime containers already
  get uv's benefit at build time (`uv sync` into a venv baked onto `PATH`);
  switching `ENTRYPOINT` to `uv run` would add per-invocation overhead on a
  hot path (every ECS task launch) for a dependency set that's already
  locked and frozen into the image — pure loss, no gain.
- [Stdlib-only heredoc scripts scope](.) — out of scope by default. The
  `python3 -c`/`python3 - <<PY` calls throughout `infra/scripts/*.sh` import
  only stdlib (`json`, `sys`, `pathlib`), no project dependencies — the
  measured ~450ms/call `uv run` overhead would be pure cost with no
  correctness or consistency benefit, since these scripts have nothing to
  do with the locked project environment at all.
- [Scope boundary: internal automation vs. user-facing install hints](issues/01-scope-boundary-internal-vs-user-facing.md) —
  Category 1 only (this repo's own internal automation). README.md's
  published-package install line, the runbook's pip/uv dependency-table row,
  and verify-pr1/preflight.sh's operator bootstrapping hints are out of
  scope. `docs/runbook.md`/`pipeline-setup.md`'s `dbt` invocation lines were
  never actually ambiguous and stay in scope (Ticket 03, now unblocked).
  `examples/dashboard/README.md`'s bare `pip install` — confirmed drift
  against CLAUDE.md's own `uv pip install` dev command for the same
  directory — graduates to Ticket 04.
- [snowflake-cli-labs multi-step CI pattern](issues/02-snowflake-cli-uv-pattern.md) —
  `uv tool install snowflake-cli-labs` (persistent PATH shim), not
  `uv run --with`/`uvx` (both are per-call-site prefixes over an ephemeral
  or dedicated-cache environment, neither puts a bare `snow` binary on PATH).
  `smoke-test.yml` needs `snow` as a bare command across multiple steps
  *and* inside an external script it doesn't control
  (`scripts/test/smoke-test-single-cik.sh`'s internal `snow_sql()` calls) —
  uv's own docs name that exact shape as the case for `uv tool install`.

## Not yet specified

None currently — Ticket 01's scope-boundary answer resolved every open fog
item this map had.

## Out of scope

- Public-facing package-install instructions: README.md's
  `pip install "edgartools>=5.29.0"` (installing the *published* PyPI
  package into an unrelated consumer project), `docs/runbook.md`'s
  dependency-table `pip / uv` bootstrapping row, and
  `scripts/verify-pr1/*`/`scripts/ops/preflight.sh`'s operator-facing `snow`
  install hints. Category 2 per
  [Ticket 01](issues/01-scope-boundary-internal-vs-user-facing.md) — none of
  these are this repo's own internal automation reaching for bare pip.
