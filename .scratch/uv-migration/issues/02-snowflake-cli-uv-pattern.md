# Research: uv-native pattern for snowflake-cli-labs in a multi-step CI workflow

Type: research
Status: resolved

## Question

`smoke-test.yml:46` runs `pip install snowflake-cli-labs --quiet`, then
(presumably) uses the installed `snow` CLI across multiple subsequent steps
in the same job. `dbt-snowflake` has an established one-shot pattern in this
repo (`uv run --with dbt-snowflake dbt run ...`) because it's invoked once
per call site — does the same `--with` pattern work cleanly across
*multiple, separate* workflow steps that each need the `snow` binary on
`PATH`, or does `uv tool install snowflake-cli-labs` / `uvx --from
snowflake-cli-labs snow` fit this shape better? Research uv's own docs
(`uv run --with`, `uv tool install`, `uvx`) for the actual persistence
semantics across steps in a GitHub Actions job, and report which pattern
correctly makes `snow` available for N later steps without re-installing
per step.

## Answer

**Confirmed multi-step usage first.** `smoke-test.yml` uses the `snow` binary
as a bare command in at least two separate `run:` steps after install
(line 46): the "Validate snow connection" step (line 74,
`snow sql --connection edgartools-dev ...`) and the "Run single-CIK smoke
test" step (line 88), which shells out to
`scripts/test/smoke-test-single-cik.sh` — an external script that itself
calls bare `snow sql ...` internally via its own `snow_sql()`/`snow_scalar()`
helper functions (lines 107-134). So this is not just "N workflow-YAML
steps" — one of the call sites is *inside a version-controlled shell script
GitHub's YAML doesn't directly own*, which turns out to matter (see below).

**Recommendation: `uv tool install snowflake-cli-labs`, not `uv run --with`
or `uvx`.**

### 1. Does `uv run --with <pkg>` persist/cache across separate process invocations?

Partially, and not in the way that matters here. The uv CLI reference's own
description of `--with` says the environment it creates is explicitly
**ephemeral**:

> "--with ... Run with the given packages installed. When used in a project,
> these dependencies will be layered on top of the project environment in a
> separate, **ephemeral environment**."
> — https://docs.astral.sh/uv/reference/cli/#uv-run (confirmed via direct
> fetch of the rendered CLI reference page)

Separately, uv's own "Relationship to uv run" note (in the Tools concept
doc) states that `uv tool run <name>` (== `uvx <name>`) is "nearly
equivalent to" `uv run --no-project --with <name> -- <name>`, but lists as
one of the **differences**: "The temporary environment [for `uv tool
run`/`uvx`] is cached in a dedicated location."
— https://docs.astral.sh/uv/concepts/tools/#relationship-to-uv-run

The implication, stated by uv's own docs, is that `uv tool run`/`uvx` gets a
dedicated, reused environment cache that plain `uv run --with` does not get
the same way. What **is** shared across invocations for `--with` is the
lower-level *package cache* (downloaded/built wheels), which is
machine-/filesystem-wide and persists across process invocations:

> "uv uses aggressive caching to avoid re-downloading (and re-building)
> dependencies that have already been accessed in prior runs."
> — https://docs.astral.sh/uv/concepts/cache/#dependency-caching

So a second `uv run --with snowflake-cli-labs snow ...` in a later CI step
would not re-download/re-build the wheel (fast, cache-linked), but it still
re-resolves and re-links a fresh ephemeral environment on every single
invocation — it is not "install once, reuse the same live environment
across steps" the way `uv tool install` is.

More importantly for this specific case: `--with` (like `uvx`) only works as
a **command prefix** — every call site that needs `snow` must be rewritten
to `uv run --with snowflake-cli-labs snow ...`. That's fine for
`dbt-snowflake`, which this repo invokes at exactly one call-site *shape*
(`uv run --with dbt-snowflake dbt run ...`, always from a script/command the
repo directly controls). It does not work cleanly here because one of the
`snow` call sites is inside `scripts/test/smoke-test-single-cik.sh`'s
internal `snow_sql()`/`snow_scalar()` helpers, which call bare `snow`
multiple times — using `--with` would require either rewriting that script
to prefix every internal `snow` call, or exporting some wrapper/alias, both
of which defeat the purpose of a one-shot per-invocation tool pattern.

### 2. What does `uv tool install <pkg>` do differently?

It creates a **persistent** virtual environment and a **persistent PATH
shim**, not a per-invocation ephemeral one:

> "Tools can also be installed with `uv tool install`, in which case their
> executables are available on the PATH — an isolated virtual environment is
> still used, but it is not removed when the command completes."
> "When installing a tool with `uv tool install`, a virtual environment is
> created in the uv tools directory. The environment will not be removed
> unless the tool is uninstalled."
> "Tool executables are symlinked into the executable directory on Unix ...
> The executable directory must be in the PATH variable for tool executables
> to be available from the shell. If it is not in the PATH, a warning will
> be displayed. The `uv tool update-shell` command can be used to add the
> executable directory to the PATH in common shell configuration files."
> — https://docs.astral.sh/uv/concepts/tools/ (Execution vs installation /
> Tool environments / Tool executables sections, confirmed via direct fetch)

After `uv tool install snowflake-cli-labs` runs once, plain `snow ...` (no
`uv run`/`uvx` prefix at all) works in every later step and inside any
external script, identically to how `pip install snowflake-cli-labs`
behaves today — this is the direct drop-in replacement.

uv's own docs state the exact use case that matches this repo's shape,
almost verbatim:

> "In most cases, executing a tool with `uvx` is more appropriate than
> installing the tool. Installing the tool is useful if you need the tool to
> be available to other programs on your system, **e.g., if some script you
> do not control requires the tool**, or if you are in a Docker image and
> want to make the tool available to users."
> — https://docs.astral.sh/uv/concepts/tools/#execution-vs-installation

`scripts/test/smoke-test-single-cik.sh` is exactly that case: a script whose
`snow_sql()`/`snow_scalar()` helpers call bare `snow` internally, unaware of
and not written for a `uv run --with`/`uvx` prefix.

**Practical caveat (not this ticket's implementation, flagging for whoever
wires it into the YAML):** the executable directory (`$HOME/.local/bin` by
default per
https://docs.astral.sh/uv/reference/storage/#storage-directories) must be on
`PATH` for the later steps to find bare `snow`. `uv tool update-shell`
edits shell rc files, which GitHub Actions' non-interactive step shells
don't source — the reliable approach in a GitHub Actions job is
`echo "$HOME/.local/bin" >> "$GITHUB_PATH"` right after the install step (or
confirm it's already on `ubuntu-latest`'s default `PATH`), not relying on
`uv tool update-shell`.

### 3. Is `uvx` semantically identical to `uv run --with` here?

No — `uvx` is identical to `uv tool run`, not to `uv run --with`:

> "Because it is very common to run tools without installing them, a `uvx`
> alias is provided for `uv tool run` — the two commands are **exactly
> equivalent**."
> — https://docs.astral.sh/uv/concepts/tools/#the-uv-tool-interface

`uvx`/`uv tool run` does get its own dedicated environment cache (distinct
from `--with`'s ephemeral one):

> "When running a tool with `uvx`, a virtual environment is stored in the uv
> cache directory and is treated as disposable ... The environment is only
> cached to reduce the overhead of repeated invocations. If the environment
> is removed, a new one will be created automatically."
> — https://docs.astral.sh/uv/concepts/tools/#tool-environments

So `uvx snow ...` would be faster on repeat invocations than
`uv run --with snowflake-cli-labs snow ...` (cached environment vs.
re-linked ephemeral one), but it shares the same structural problem as
`--with` for this ticket: it's a per-call-site prefix, not a PATH-resident
binary, so it still can't satisfy `smoke-test-single-cik.sh`'s bare internal
`snow` calls without rewriting that script.

### 4. Recommended pattern for "install once, use across N later CI steps"

`uv tool install snowflake-cli-labs` in the first step (replacing the
`pip install snowflake-cli-labs --quiet` line at `smoke-test.yml:46`), with
`$HOME/.local/bin` confirmed/added to `$GITHUB_PATH` in that same step. All
downstream steps — including the ones inside
`scripts/test/smoke-test-single-cik.sh` that this research-only ticket does
not modify — keep calling bare `snow ...` exactly as they do today. This is
the pattern uv's own docs point to for "a script you do not control requires
the tool," which is precisely this repo's shape, and is structurally
different from the `dbt-snowflake` site: `dbt-snowflake` is invoked as a
single per-command-site tool (`uv run --with dbt-snowflake dbt run ...`),
while `snowflake-cli-labs`'s `snow` binary is a PATH-resident dependency
consumed by both CI YAML steps and an external script — the shape `uv tool
install` is designed for, not `uv run --with`/`uvx`.

### Sources consulted (primary only)

- https://docs.astral.sh/uv/concepts/tools/ (Tools concept doc — execution
  vs installation, tool environments, tool executables, relationship to
  `uv run`)
- https://docs.astral.sh/uv/reference/cli/#uv-run (`--with` flag exact
  description)
- https://docs.astral.sh/uv/concepts/cache/ (dependency caching, CI caching
  guidance, cache directory semantics)
- https://docs.astral.sh/uv/reference/storage/ (storage directory layout —
  cache dir vs. persistent data dir vs. temporary dir; script virtual
  environments live in the cache dir)
- https://docs.astral.sh/uv/concepts/projects/run/ (`uv run --with` /
  requesting additional dependencies)
- https://docs.astral.sh/uv/guides/scripts/ (script `--with` usage examples)
