# Scope boundary: internal automation vs. user-facing install hints

Type: grilling
Status: open

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
