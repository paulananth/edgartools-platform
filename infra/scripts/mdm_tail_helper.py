"""Shared MDM Tail Sequencing Skeleton, plus the single MDM machine's
nested-execution call site (state-machine-consolidation wayfinder map,
tickets 02 and 07 respectively).

wire_mdm_tail (ticket 02): the proven drift risk (git log -S"MdmVerify",
commit 3aa92fe9) was MdmExport-before-MdmSync ordering (renamed to
Publish-before-"Publish Relationships" by mdm-stage-renaming ticket 01),
not the whole tail's flags/Catch/retry shape -- those genuinely differ per
MDM Pipeline Machine (see the ticket's addendum) and stay caller-owned.
This wires already-built Publish/"Publish Relationships"/Reconcile state
dicts into the correct, data-architecture-mandated order
(docs/data-architecture.md Issue 3) and optionally appends GoldRefresh --
nothing more. Still used by the 4 MDM Pipeline Machines whose fate ticket
07 left open (ownership_mdm_gold, silver_mdm_gold,
bronze_seed_silver_gold's default path, residual_holds_graph) --
unaffected by ticket 07's own machine (below), which folded a superset of
this same tail (plus Mastering and BackpropagateIdsToSilver) into a real,
separately-deployed nested machine instead of code-level sharing, for
daily_incremental/load_history/the seed machine specifically. mdm_gold
(ticket 07: deleted -- it had no head, fully redundant with the new
machine) was this function's 5th caller; the remaining 4 are ticket 08's
open question, not this one.

call_mdm_machine (ticket 07): every command inside the single MDM machine
(write_mdm_definition, deploy-aws-application.sh) reads $.run_id, not
$$.Execution.Name -- inside a nested execution, $$.Execution.Name resolves
to THAT execution's own auto-generated name, not the calling machine's
(confirmed live via AWS's own nested-execution semantics; would otherwise
silently fragment one logical run's MDM Run Identity, CONTEXT.md, across
disconnected identities -- Ticket 30 (e45bcd30) added durable per-run
binding columns to MDM Postgres tables that depend on this staying one
value per logical run). This helper is the one place that wires the
$$.Execution.Name -> $.run_id handoff, shared by every caller
(daily_incremental, load_history, the seed machine) so the handoff can't
independently drift or go missing at one call site while present at
another.

Deploy-aws-application.sh's Python heredocs import this module via
sys.path.insert(0, SCRIPT_DIR) so every caller shares the exact same
wiring instead of hand-typing Next pointers or Input shapes.
"""
from __future__ import annotations


def call_mdm_machine(state_machine_arn, next_state=None, is_end=False, retry_secs=120):
    """Start the single MDM machine as a synchronous nested execution.

    Propagates the calling execution's own $$.Execution.Name as this
    nested execution's `run_id` input field -- see this module's own
    docstring for why that hop can't be skipped. Uses
    states:startExecution.sync:2 (not .sync:1) so the nested execution's
    Output is returned already parsed as JSON rather than as an escaped
    string; nothing here currently reads that output, but a caller added
    later doesn't have to discover the .sync:2-vs-.sync distinction itself.
    """
    if next_state is None and not is_end:
        raise ValueError("call_mdm_machine requires next_state or is_end=True")
    s = {
        "Type": "Task",
        "Resource": "arn:aws:states:::states:startExecution.sync:2",
        "Parameters": {
            "StateMachineArn": state_machine_arn,
            "Input": {
                "run_id.$": "$$.Execution.Name",
                "AWS_STEP_FUNCTIONS_STARTED_BY_EXECUTION_ID.$": "$$.Execution.Id",
            },
        },
        "Retry": [{
            "ErrorEquals": ["States.TaskFailed"],
            "IntervalSeconds": retry_secs,
            "BackoffRate": 2.0,
            "MaxAttempts": 2,
        }],
    }
    if is_end:
        s["End"] = True
    else:
        s["Next"] = next_state
    return s


def wire_mdm_tail(export_state, sync_state, verify_state, gold_state=None):
    """Chain Publish -> Publish Relationships -> Reconcile (-> GoldRefresh).

    Each *_state argument is a fully-built ASL Task state dict (its own
    command expression, task-definition ARN, Retry, and Catch already
    applied by the caller). Any pre-set Next/End on export/sync/verify is
    overwritten; gold_state's End is set unconditionally. This function has
    no opinion about what's inside each state -- callers may pass a
    sync_state with extra flags (e.g. --generation-id) or a verify_state
    with its own Catch clause, and they pass through unchanged.

    Returns the four (or three, if gold_state is None) states keyed by
    their ASL state name, ready to merge into a machine's States dict.
    """
    export_state = dict(export_state)
    sync_state = dict(sync_state)
    verify_state = dict(verify_state)

    export_state.pop("End", None)
    export_state["Next"] = "Publish Relationships"

    sync_state.pop("End", None)
    sync_state["Next"] = "Reconcile"

    states = {"Publish": export_state, "Publish Relationships": sync_state}

    if gold_state is not None:
        verify_state.pop("End", None)
        verify_state["Next"] = "GoldRefresh"
        gold_state = dict(gold_state)
        gold_state.pop("Next", None)
        gold_state["End"] = True
        states["Reconcile"] = verify_state
        states["GoldRefresh"] = gold_state
    else:
        verify_state.pop("Next", None)
        verify_state["End"] = True
        states["Reconcile"] = verify_state

    return states
