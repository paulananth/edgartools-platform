# Connect whole-publication name preparation to the normal load

Status: claimed
Type: task

The operator's Lavish annotation on the Company architecture atlas was "close this gap".
They selected "Use automatic preparation (recommended)": prepare the whole-publication
pairs before the scoped read, keeping name binding after identifier matching.

- [x] 2026-11-11 21:43 ET Connect configured preparation before scope derivation; loader ordering and failure-before-submission tests pass.
- [x] 2026-11-11 21:43 ET Reuse the pairing and pair-application helpers; recipe/count/lookup checks share one implementation, with explicit source-declared completeness and strict full-file selection.
- [x] 2026-11-11 21:43 ET Prove unique, ambiguous, changed-input, unchanged-repeat and interrupted behavior on invented captures; PostgreSQL and MySQL each pass all 27 mastering adapter tests, including both delivery orders and atomic release failure/retry.
- [x] 2026-11-11 21:43 ET Run affected checks: 370 tests passed in 68 s, 11 guide/input checks passed, Mapping Document check passed, and final focused cache/loader tests rerun after repairs.
- [x] 2026-11-11 21:43 ET Review Standards, Spec and GoF; completeness and split-commit findings fixed and reviewed again. No remaining findings.
- [ ] Publish the PR and verify its final head in CI.
- [ ] Update the architecture atlas to the verified implementation and report its limits.
- [x] 2026-11-11 21:43 ET Learning → skill: `data-operations` names configured preparation before deriving scope; `mdm-engineering` requires durable pair evidence, lookup keys and waiter release in one transaction.

## Investigation

The normal GLEIF target reads its approved scope before `mastering.merge`. Calling
the pairing helper only afterward would leave newly paired LEIs outside the reading.
The existing `waterfall.pairs` helper also expects external publisher metadata; retained
capture receipts carry hashes and sizes only. Preserve that strict API for callers
with publisher metadata. The automatic path must describe its evidence as the source's
declared complete capture, verified through EOF and the declared count, without
inventing a publisher timestamp or claiming independent provider completeness.

GoF consult: leave the existing functional helpers and loader structure in place.
Recent history adds declared run-input derivation and local reading; it does not
justify a new class hierarchy. A configured operation registry provides the required
variation without source-name branches in the loader.

## Behavior corrections exposed by the normal path

- SEC-first then GLEIF failed on the old helper: the golden record retained only one subject rather than both.
  The helper had saved a name lookup key but left the stored holder body without the computed pair evidence.
  The same transaction now retains both, so the later file can pass the existing name rule.
- The helper previously committed pair application before releasing waiting records. A release failure left a
  durable key which made retry return early. Pair evidence, keys, mastering and release now commit together;
  the fault test observes the writes inside the transaction, then verifies rollback and a successful retry.
- Automatic preparation and derived scope use the selected worker environment, rather than an ambient login.
- Cache identity contains the normalized facts the pass consumes, captured receipt, recipe, policy and runtime.
  Saving the derived answer does not invalidate its own cache. A cached projection still checks the compressed
  capture's hash; changed bytes with an unchanged receipt are refused before applying a pair.

## Review

### Standards

Pass after repairs. An explicit approved `full_publication` declaration and exact full-file basename select the
retained full capture; same-count delta, partial and unrecognized filenames are refused. The receipt claims only
source-declared completeness, with no invented publisher date. Selected-worker connections, generic dispatch,
destination locking and atomic recovery were reviewed. Shared skill additions contain no source-specific names.

### Spec

Pass for the operator's selected automatic-preparation approach. Preparation precedes scope; actual name binding
remains after identifier matching. Both delivery orders, scope expansion, ambiguity and unchanged repeat are
covered. Existing accepted bindings are not silently undone when a later population makes a name ambiguous.

### GoF

Leave the functional helpers and narrow preparation registry in place. Recent changes show orchestration work,
not repeated variation that justifies a class hierarchy. The new store operation preserves the existing atomic
Merge Stage boundary.

## Qualification boundary

This change is implemented and fixture-tested on PostgreSQL and MySQL. It performs no source activation,
provider request, production load or migration. Full retained-delivery qualification, independent publisher
completeness and live deployment remain separate from these tests; the broader work remains in ticket 212.
