"""Choose one source-onboarding owner and next action from supplied evidence."""

from __future__ import annotations

from collections.abc import Mapping


_REQUEST_KEYS = {
    "source_configured",
    "delivery_changed",
    "live_rules_changed",
    "resume_phases",
}
_PHASE_KEYS = {"owner", "action", "complete", "hashes_match"}


def route_next_action(request: Mapping[str, object]) -> dict[str, str]:
    """Return one owner/action pair from normalized configuration and run evidence."""
    unknown = request.keys() - _REQUEST_KEYS
    if unknown:
        raise ValueError(
            f"unsupported route request fields: {', '.join(sorted(unknown))}"
        )

    configured = request.get("source_configured")
    delivery_changed = request.get("delivery_changed")
    live_rules_changed = request.get("live_rules_changed")
    for field, value in (
        ("source_configured", configured),
        ("delivery_changed", delivery_changed),
        ("live_rules_changed", live_rules_changed),
    ):
        if type(value) is not bool:
            raise ValueError(f"{field} must be a boolean")

    if not configured:
        return {
            "owner": "Data Onboarding",
            "action": (
                "Start onboarding from the retained capture and keep the profiling "
                "report and findings with the handoff."
            ),
        }

    phases = request.get("resume_phases")
    if phases is not None:
        if not isinstance(phases, list) or not phases:
            raise ValueError("resume_phases must be a non-empty list when supplied")
        for phase in phases:
            if not isinstance(phase, Mapping) or phase.keys() != _PHASE_KEYS:
                raise ValueError(
                    "each resume phase must contain owner, action, complete, and hashes_match"
                )
            owner = phase["owner"]
            action = phase["action"]
            complete = phase["complete"]
            hashes_match = phase["hashes_match"]
            if (
                not isinstance(owner, str)
                or not owner.strip()
                or not isinstance(action, str)
                or not action.strip()
            ):
                raise ValueError("resume phase owner and action must be non-empty strings")
            if type(complete) is not bool or type(hashes_match) is not bool:
                raise ValueError("resume phase complete and hashes_match must be booleans")
            if not hashes_match or not complete:
                return {"owner": owner, "action": action}

    if live_rules_changed and delivery_changed:
        return {
            "owner": "Data Platform",
            "action": (
                "Ask the operator to confirm the intended next handoff because "
                "both live rules and the selected delivery changed."
            ),
        }

    if live_rules_changed:
        return {
            "owner": "Refining Rules",
            "action": (
                "Compare the approved live rules with the changed delivery; do not "
                "switch on a rules version."
            ),
        }
    if delivery_changed:
        return {
            "owner": "Data Operations",
            "action": (
                "Review the selected delivery and current Bookkeeping and Change "
                "Journal status; hand off to the existing Data Operations path."
            ),
        }
    return {
        "owner": "Data Operations",
        "action": (
            "Check the current run and delivery status, then hand off to Data "
            "Operations without repeating completed work."
        ),
    }
