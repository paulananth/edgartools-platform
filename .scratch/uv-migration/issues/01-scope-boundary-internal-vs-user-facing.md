# Scope boundary: internal automation vs. user-facing install hints

Type: grilling
Status: resolved

## Question

This repo has two different flavors of "pip install" text, and they may not
belong to the same problem:

1. **Internal automation** this repo runs itself: CI workflows
   (`.github/workflows/ci.yml:96`, `smoke-test.yml:46`), deploy scripts.
   These are the repo's own tooling invoking Python/CLI tools — CLAUDE.md's
   "never invoke bare pip" rule clearly targets these.
2. **User-facing install hints**: README.md's `pip install
   "edgartools>=5.29.0"` (instructing someone installing the *published*
   PyPI package into *their own, unrelated* project), `docs/runbook.md`'s
   dependency table (`| pip / uv | latest | bundled or \`pip install uv\` |`),
   `scripts/verify-pr1/*` and `scripts/ops/preflight.sh`'s comments/error
   messages telling an operator how to install the `snow` CLI on their own
   machine before running these scripts.

Does this migration's destination cover category 2 at all, or is it
category-1-only? If category 2 is out of scope, several "Not yet specified"
fog items on the map collapse immediately (the runbook dependency table, the
verify-pr1 install hints, examples/dashboard's standalone README). If it's
in scope, they become real tickets needing their own site-by-site review.

## Recommendation

Category 1 only. A person installing the published `edgartools-platform`
PyPI package, or installing `snow`/`uv` itself onto a fresh machine before
this repo's tooling can even run, isn't operating inside this repo's uv-
managed environment yet — telling them "pip install uv" or "pip install
snowflake-cli-labs" as a bootstrapping instruction isn't the same class of
problem as this repo's *own* scripts silently reaching for bare pip instead
of the uv workflow they're supposed to already be running under.

## Answer

Confirmed: category 1 only. Concretely:

- **Out of scope** (category 2, no ticket needed): README.md's
  `pip install "edgartools>=5.29.0"` (published-package install instruction
  for an unrelated consumer project), `docs/runbook.md`'s dependency table
  row (`| pip / uv | latest | bundled or \`pip install uv\` |` — a
  bootstrapping hint, not this repo's own tooling), and
  `scripts/verify-pr1/*`/`scripts/ops/preflight.sh`'s comments/error
  messages telling an operator how to install `snow` on their own machine
  before these scripts can run at all.
- **Still in scope, unaffected by this answer**: `docs/runbook.md`'s `dbt
  deps`/`dbt run --target prod`/`dbt test --target prod` lines and
  `edgar/ai/skills/platform/pipeline-setup.md`'s `dbt run`/`dbt test`
  lines were never actually the ambiguous case — a documented procedure for
  invoking *this repo's own* dbt project is squarely "Python CLI execution"
  under CLAUDE.md's uv convention regardless of the category-1/2 boundary.
  Already tracked as [Ticket 03](03-audit-dbt-invocation-sites.md), which
  this resolution unblocks.
- **Newly in scope, graduated to a ticket**: `examples/dashboard/README.md`
  (`pip install -r examples/dashboard/requirements.txt`, line 45) is real,
  confirmed drift against CLAUDE.md's own documented dev command for the
  exact same directory (`uv pip install -r requirements.txt`) — this is
  category 1 (this repo's own dev setup for a directory it already
  prescribes uv for), not a category-2 published-package install hint. See
  [Ticket 04](04-fix-examples-dashboard-pip-install-drift.md).
