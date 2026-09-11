Status: ready-for-agent

# Shared Stage-Builder Functions for load_history / daily_incremental

## Problem Statement

`load_history` and `daily_incremental` are the two Step Functions pipelines
that fetch and process SEC data at scale. Adding a new data pipeline stage
to either one — or keeping the same stage wired consistently into both —
currently means hand-copying a ~30-40 line block of Step Functions JSON
(a Distributed Map wrapping an ECS task invocation, or a Force-check
Choice/Fetch/FetchForced/Ingest trio) and manually keeping every copy in
sync by eye. This has already happened twice for real (ADV bulk fetch and
Firm Roster fetch, each hand-copied into both pipelines, with the second
copy's own comment admitting it is kept in sync manually), and an
already-approved plan to bring three more fundamentals-extraction modes
into `daily_incremental` would create a third and fourth round of the same
copy-paste, this time diverging further because `daily_incremental`'s
version doesn't need the CIK-windowed Distributed Map fan-out
`load_history`'s version does. Every future change to a shared property —
a task's compute profile, a retry policy, a failure-catch target's shape —
has to be found and applied by hand in every copy, with nothing catching a
missed one.

## Solution

Two small, shared factory functions that assemble the two recurring stage
shapes from a handful of parameters, replacing the hand-copied JSON blocks
in both pipeline-definition builders. Adding a new pipeline stage of
either shape becomes one function call with the right parameters, in
whichever pipeline(s) it belongs to, instead of a copy-pasted block. The
existing three fundamentals modes and the existing ADV/Firm-Roster pairs
are migrated onto the shared functions as part of this change, so the
mechanism is proven against real, already-wired pipelines before any new
pipeline uses it — not shipped as an unused abstraction.

## User Stories

1. As a platform engineer adding a new SEC-data extraction mode to
   `load_history`, I want a single function call that produces the
   Distributed-Map-wrapped stage, so that I don't have to hand-copy an
   existing mode's block and edit every field that differs.
2. As a platform engineer bringing that same mode into `daily_incremental`,
   I want the identical function to also produce a non-windowed (flat,
   single-task) version of the same stage, so that the two pipelines'
   versions of one conceptual stage can never drift into two different,
   independently-maintained shapes.
3. As a platform engineer adding a new force-capable fetch pipeline (in the
   shape ADV bulk and Firm Roster already use), I want a single function
   call that produces the Force-check Choice plus Fetch/FetchForced/Ingest
   trio, so that I don't re-derive the same three-state wiring by hand.
4. As a platform engineer maintaining an existing force-capable fetch
   pipeline that is wired into both `load_history` and
   `daily_incremental`, I want both pipelines' copies to come from the
   same function call, so that a change to one automatically keeps the
   other in sync instead of requiring a manual, easy-to-forget second edit.
5. As a platform engineer changing a stage's task compute profile (as
   already happened once for the three fundamentals modes, moved from a
   medium to a large ECS task profile together after an OOM incident), I
   want to change it in one place, so that every pipeline using that stage
   picks up the change without a manual sweep across the file.
6. As a platform engineer changing the failure-handling policy for a class
   of stage (e.g. the AD-13 non-fatal Catch-and-continue convention already
   used by every fundamentals mode and every force-capable fetch), I want
   that policy encoded once in the shared function, so that a new stage of
   the same shape gets the correct failure behavior by construction, not by
   remembering to copy the right `Catch` block.
7. As a platform engineer reviewing a pull request that adds a new
   pipeline stage, I want to see a short, parameterized function call
   instead of a 30-40 line JSON block, so that the review can focus on
   whether the parameters are right rather than re-deriving the JSON shape
   from scratch.
8. As a platform engineer debugging why a stage in `daily_incremental`
   behaves differently from its counterpart in `load_history`, I want any
   real difference between the two to be visible as an explicit parameter
   difference at the call site, so that I am not left diffing two
   hand-written JSON blocks to find what actually changed.
9. As a platform engineer, I want the existing three fundamentals modes
   (entity-facts, per-filing, thirteenf) and the existing two force-capable
   fetch pipelines (ADV bulk, Firm Roster) migrated onto the new shared
   functions as part of this change, so that the mechanism is validated
   against real, already-load-bearing pipelines rather than shipped
   untested and unused.
10. As a platform engineer running the existing architecture test suite
    after this change, I want the generated Step Functions definitions for
    both pipelines to be byte-identical to what they were before the
    refactor, so that I have concrete proof this change altered no
    observable behavior.
11. As a platform engineer who later implements the already-approved plan
    to wire the three fundamentals modes into `daily_incremental`
    (a plan that predates this change), I want that implementation to call
    the same shared function `load_history` already uses for those modes,
    so that the new wiring is a call with `windowed` set to the
    non-windowed case, not a fourth hand-copied block.
12. As a platform engineer, I want the two shared functions to live in a
    real, importable Python module both pipeline builders already have a
    proven way to reach, so that they are genuinely shared code rather than
    two more copies of the same text.

    **Correction after reading the actual code (superseding the original
    version of this story):** `write_load_history_definition` and
    `write_warehouse_mdm_gold_definition` are bash functions that each
    invoke their own independent `python3 -` subprocess via a heredoc —
    confirmed by the file's own existing comments, which twice already
    state outright that these two functions "can't share code" for exactly
    this reason. A plain function defined in one heredoc's text is invisible
    to the other's. The file already has a proven answer to this: a small
    sibling `.py` module (`mdm_tail_helper.py`) that both heredocs import via
    `sys.path.insert(0, SCRIPT_DIR)`, used today for the MDM-tail wiring
    every MDM-invoking pipeline shares. The two new functions belong in a
    new sibling module of the same kind, imported the same way — not as
    bare functions dropped into the deploy script's own text.
13. As a platform engineer, I want the shared functions to cover exactly
    the two shapes that have already recurred (windowed/non-windowed mode
    stage; force-capable fetch trio), not a single do-everything builder
    covering both, so that neither function accumulates parameters for a
    shape it doesn't actually need.
14. As a platform engineer, I want each shared function's parameters to
    correspond to the things that have actually varied between existing
    copies (mode/command identifier, task compute profile, windowed
    yes/no, the success-path next-state, the failure-path next-state, and
    for the fetch trio the dataset-period-style argument), not to every
    conceivable future variation, so that the function stays a faithful
    generalization of what already exists rather than a speculative one.
15. As a platform engineer, I want the file's own separately-duplicated
    single-ECS-task-state helper to be left untouched by this change
    unless it turns out to block the two new functions' implementation, so
    that this change stays scoped to the two duplication axes it was
    chartered to fix.

## Implementation Decisions

- **Corrected during implementation, superseding this section's original
  "same script, no new module" decision:** `write_load_history_definition`
  and `write_warehouse_mdm_gold_definition` are bash functions, each
  running its own independent `python3 -` subprocess against a heredoc —
  there is no shared Python runtime between them, confirmed by the file's
  own pre-existing comments stating this outright. The two new functions
  live in a new sibling Python module next to the deploy script, imported
  by both heredocs via `sys.path.insert(0, SCRIPT_DIR)` — the exact,
  already-proven mechanism `mdm_tail_helper.py` established for this same
  problem (sharing MDM-tail wiring across the same subprocess boundary).
  This is a new file, but not a new pattern for this codebase — it is the
  established one, applied a second time.
- The first function assembles a "pipeline-stage" shape: one ECS task
  invocation for a given mode/command and task-definition ARN, optionally
  wrapped in a Distributed Map (reading the same CIK-window manifest
  `load_history`'s existing windowed stages already read) when a
  `windowed` flag is set, with the established non-fatal Catch-and-continue
  failure policy routing to a caller-supplied next state on any failure,
  and a caller-supplied next state on success. `load_history`'s three
  existing fundamentals-mode stages (entity-facts, per-filing, thirteenf)
  are rebuilt through this function with `windowed=True`; the
  already-approved future work that brings those same three modes into
  `daily_incremental` is expected to call this same function with
  `windowed=False`, per that plan's own statement that the daily case
  needs a single task invocation, not CIK-windowed fan-out.
- The second function assembles a "force-capable fetch" shape: a
  Force-check Choice state (routing on whether the caller's input
  requested a forced re-fetch) followed by a Fetch-or-FetchForced ECS task
  invocation and a subsequent Ingest ECS task invocation, parameterized by
  the fetch command's name, its dataset-period-style argument, the task
  ARN, and the success/failure next-state targets. The two existing
  pipelines using this shape today (ADV bulk fetch, Firm Roster fetch) are
  rebuilt through this function in both `load_history` and
  `daily_incremental`, replacing the two independent hand-copied pairs
  that exist today (four copies total, two per pipeline) with calls to one
  function.
- Both functions preserve every existing, already-decided policy detail
  exactly as it exists in the current hand-written blocks — the specific
  tolerated-failure percentage, concurrency limit, retry/backoff settings,
  and the AD-13 non-fatal Catch convention are carried into the function
  as fixed behavior for that shape, not exposed as new parameters, unless
  a genuine difference between two existing copies requires it to be
  parameterized to preserve current behavior exactly.
- The existing single-ECS-task-state helper that both new functions build
  on internally is out of scope for consolidation in this change unless
  the two new functions cannot be written cleanly without first
  consolidating it — this change is scoped to the two higher-level
  duplication axes identified, not every duplication in the file.
- No change to either pipeline's actual runtime behavior, task profiles,
  failure-handling policy, or state names is intended by this change —
  every existing call site is expected to produce output identical to
  what it produces today.

## Testing Decisions

- A good test here asserts on the generated Step Functions JSON shape
  (external, observable behavior of the definition-building code), not on
  the internal Python control flow used to assemble it.
- The existing architecture-level tests that already call the two
  pipeline-definition builders and assert on their generated JSON are
  extended, not replaced: for each of the five migrated stages (three
  fundamentals modes, two force-capable fetches), a new assertion confirms
  the function-produced JSON is identical to what the pre-refactor
  hand-written block produced, giving direct regression proof that this
  change altered no observable pipeline behavior.
- In addition, each of the two new functions gets its own direct unit test
  exercising it in isolation (not only through the full pipeline-definition
  builders): one test per function covering its windowed/non-windowed (or
  force/non-force) branches, its success-path wiring, and its failure-path
  wiring, following this repository's existing convention of pairing a
  focused unit test with a broader architecture-level test for
  infrastructure-definition code.
- Prior art: the existing state-machine architecture tests for both
  pipelines already exercise this exact code path end to end and are the
  direct precedent for the first seam; this repository's existing
  small-helper unit tests elsewhere in the same file's test suite are the
  precedent for the second.

## Out of Scope

- Implementing the already-approved plan to wire the three fundamentals
  modes into `daily_incremental` (that work has its own tracked plan and
  tickets already; this spec only ensures the shared function it should
  call exists and is proven before that work begins).
- Consolidating the file's separately-duplicated single-ECS-task-state
  helper, unless required to implement the two functions above cleanly.
- Any change to a pipeline's actual task profile, concurrency,
  tolerated-failure percentage, or failure-routing target — this is a
  structural refactor of how existing, already-decided behavior is
  expressed, not a change to the behavior itself.
- Any new pipeline stage that doesn't already exist today — this spec
  covers building and proving the mechanism against existing pipelines,
  not authoring new ones.
- Any change to how either pipeline is deployed, versioned, or rolled
  back.

## Further Notes

This spec was produced from a live `/gof-pattern-selector` diagnosis run
against the current codebase: both duplication axes described above were
confirmed by reading the actual generated-JSON blocks and their governing
comments (including one block's own comment admitting the cross-pipeline
copy is "kept in sync" by hand), not inferred. The recommendation was a
plain factory function for each axis — not a GoF class hierarchy — since
the constructed objects are plain JSON-serializable dicts assembled in one
function call each, not a multi-step object-assembly problem needing a
Builder/Director pair, and not a family of products needing an Abstract
Factory. Two existing architecture test files (a combined ~1,700 lines)
already assert on both pipelines' generated definitions, giving this
refactor a real regression safety net already in place before work starts.
