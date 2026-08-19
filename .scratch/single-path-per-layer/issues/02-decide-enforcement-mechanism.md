# Decide the Enforcement Mechanism for the Single-Path Rule

Type: `wayfinder:grilling` (HITL)

Status: resolved

Blocked by: [Enumerate Every Layer Transition and Its Current
Implementation(s)](01-enumerate-layer-transitions.md)

## Question

Given Ticket 01's findings about what shapes of violation actually occur
(or don't) in this codebase, decide what mechanism will catch a *new*
single-path violation before it ships — the shard-publish-fix incident
(CLAUDE.md's "Shard-publish promotion-race 5-whys" entry: two structurally
identical write paths silently diverged, nothing caught it until three real
prod failures) is the concrete failure to weigh every candidate against.

Candidates to weigh (not exhaustive):

- An automated architecture test (e.g. asserting a fixed set of "the one
  function for transition X" symbols exist and that other call sites
  delegate to them, not reimplement them).
- A static-analysis / lint rule (feasibility depends heavily on what shape
  Ticket 01's violations turn out to have — near-duplicate function bodies
  are checkable; behavioral divergence between differently-shaped
  implementations usually isn't).
- A code-review checklist item folded into the standing
  `/gof-refactor-reviewer` pass this repo already requires before
  non-trivial changes (per CLAUDE.md).
- A naming/registry convention (e.g. every layer transition's canonical
  implementation is registered in one place, making a second, unregistered
  implementation visibly wrong).
- Some combination of the above, scoped per transition rather than one
  mechanism for all.

Weigh mechanical enforceability against cost of building/maintaining it —
this repo's own precedent (release-readiness ticket 79's fingerprint
pattern, the shard-publish fix's test suite) favors cheap, targeted checks
over heavyweight infrastructure.

## Answer (2026-08-19)

Architecture test, extending this repo's own proven precedent
(`tests/architecture/test_runtime_shim.py`'s `CompatibilityShimTests`,
which locks the shape of the runtime.py/silver.py/gold.py compatibility
shims) rather than a lint rule, checklist item, or registry convention.

Rejected the general "detect any future single-path violation" framing —
that's not mechanically checkable without heavy AST tooling, and this
repo's `/gof-refactor-reviewer` Rule 0 precedent ("the default verdict is
leave it," flag confidently only with real evidence) argues against
building general infrastructure for a problem observed exactly once.
Instead: narrow and concrete. A registry of one known "sibling pair" — the
one that has already diverged in production
(`_publish_silver_database_if_remote`/`_publish_shard_if_remote` and their
`_with_retry` wrappers) — with a test asserting they stay symmetric on the
two axes that actually diverged: which env vars the retry wrappers
reference, and whether both publish functions call
`merge_candidate_into_canonical`.

Implemented: `tests/architecture/test_sibling_path_symmetry.py`. Five
tests — three prove the env-var-extraction helper is red-capable (using
synthetic snippets, not the real functions, so detection logic is verified
independently of the current passing state), two apply it to the real
sibling pair (currently green, since the shard-publish fix already
landed). Verified against real pre-fix source (`git show eb0a60cb^:...`,
not just assumed) exactly how each assertion would have failed:
`_publish_shard_if_remote_with_retry` didn't exist pre-fix, so the env-var
test would have failed at the `import` line itself, not by exercising its
own comparison logic against a real historical env-var *drift* — that
axis's detection logic is proven only against synthetic snippets, not a
real incident. The merge-symmetry test's `assertIn` is the one whose logic
history actually exercised: `merge_candidate_into_canonical` appeared only
in the monolith function pre-fix, so that assertion would have failed on
its own terms. A `/code-review` pass (Standards + Spec sub-agents, plus an
inline `/gof-refactor-reviewer` check on the new file — nothing found
worth flagging there, it's brand new with no churn history) caught this
overstatement and one real gap: the env-var regex only matched
double-quoted `os.environ.get(...)`, so a sibling using `os.getenv(...)` or
single quotes would have silently extracted an empty set and passed as
spuriously symmetric. Both fixed — regex now matches either call form and
either quote style, with a new synthetic test (`test_extracts_getenv_and_
single_quoted_calls_too`) proving the broadened match, and the docstring
now states precisely which assertion's logic real history exercised
versus which was only proven against synthetic input. Not deliberately
reverted production code to prove the pre-fix claim, since that would mean
temporarily breaking production code for a test demonstration — `git show`
against the pre-fix commit was sufficient. Full architecture suite green
(476 passed, plus the 2 pre-existing unrelated
`test_bootstrap_dbt_snowflake_secret.py` failures present before this
change).

Scope is deliberately narrow: this locks one known-diverged pair, not
every transition Ticket 01 audited. If a future audit finds a second real
sibling-pair divergence, extend this same file with another registered
pair rather than building general detection — matching the "cheap and
targeted over heavyweight" preference this ticket's own question named.
