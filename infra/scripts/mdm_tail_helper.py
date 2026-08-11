"""Shared MDM Tail Sequencing Skeleton.

state-machine-consolidation wayfinder map, ticket 02: the proven drift risk
(git log -S"MdmVerify", commit 3aa92fe9) was MdmExport-before-MdmSync
ordering, not the whole tail's flags/Catch/retry shape -- those genuinely
differ per MDM Pipeline Machine (see the ticket's addendum) and stay
caller-owned. This module wires already-built MdmExport/MdmSync/MdmVerify
state dicts into the correct, data-architecture-mandated order
(docs/data-architecture.md Issue 3) and optionally appends GoldRefresh --
nothing more. Deploy-aws-application.sh's Python heredocs import this via
sys.path.insert(0, SCRIPT_DIR) so every MDM Pipeline Machine shares the
exact same ordering logic instead of hand-typing Next pointers.
"""
from __future__ import annotations


def wire_mdm_tail(export_state, sync_state, verify_state, gold_state=None):
    """Chain MdmExport -> MdmSync -> MdmVerify (-> GoldRefresh).

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
    export_state["Next"] = "MdmSync"

    sync_state.pop("End", None)
    sync_state["Next"] = "MdmVerify"

    states = {"MdmExport": export_state, "MdmSync": sync_state}

    if gold_state is not None:
        verify_state.pop("End", None)
        verify_state["Next"] = "GoldRefresh"
        gold_state = dict(gold_state)
        gold_state.pop("Next", None)
        gold_state["End"] = True
        states["MdmVerify"] = verify_state
        states["GoldRefresh"] = gold_state
    else:
        verify_state.pop("Next", None)
        verify_state["End"] = True
        states["MdmVerify"] = verify_state

    return states
