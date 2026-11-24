import json
import sys
from io import StringIO

from edgar_warehouse.application.source_route import route_next_action


def test_new_source_routes_to_onboarding():
    result = route_next_action(
        {"source_configured": False, "delivery_changed": False, "live_rules_changed": False}
    )

    assert result["owner"] == "Data Onboarding"
    assert "retained capture" in result["action"]


def test_changed_delivery_routes_to_operations():
    result = route_next_action(
        {"source_configured": True, "delivery_changed": True, "live_rules_changed": False}
    )

    assert result["owner"] == "Data Operations"
    assert "selected delivery" in result["action"]


def test_repeat_routes_to_operations_without_repeating_completed_work():
    result = route_next_action(
        {"source_configured": True, "delivery_changed": False, "live_rules_changed": False}
    )

    assert result["owner"] == "Data Operations"
    assert "without repeating completed work" in result["action"]


def test_live_rule_change_routes_to_refining_rules():
    result = route_next_action(
        {"source_configured": True, "delivery_changed": False, "live_rules_changed": True}
    )

    assert result["owner"] == "Refining Rules"
    assert "Compare" in result["action"]


def test_resume_skips_matching_completed_phase_and_selects_first_unfinished():
    result = route_next_action(
        {
            "source_configured": True,
            "delivery_changed": False,
            "live_rules_changed": False,
            "resume_phases": [
                {
                    "owner": "Data Profiling",
                    "action": "Keep the verified profile report",
                    "complete": True,
                    "hashes_match": True,
                },
                {
                    "owner": "Data Onboarding",
                    "action": "Map the next part",
                    "complete": False,
                    "hashes_match": True,
                },
            ],
        }
    )

    assert result == {"owner": "Data Onboarding", "action": "Map the next part"}


def test_resume_reopens_first_phase_with_changed_hashes():
    result = route_next_action(
        {
            "source_configured": True,
            "delivery_changed": False,
            "live_rules_changed": False,
            "resume_phases": [
                {
                    "owner": "Data Profiling",
                    "action": "Re-profile the changed delivery",
                    "complete": True,
                    "hashes_match": False,
                },
                {
                    "owner": "Data Onboarding",
                    "action": "Map the next part",
                    "complete": False,
                    "hashes_match": True,
                },
            ],
        }
    )

    assert result == {"owner": "Data Profiling", "action": "Re-profile the changed delivery"}


def test_completed_resume_routes_to_operations_without_repeating_work():
    result = route_next_action(
        {
            "source_configured": True,
            "delivery_changed": False,
            "live_rules_changed": False,
            "resume_phases": [
                {
                    "owner": "Data Profiling",
                    "action": "Profile",
                    "complete": True,
                    "hashes_match": True,
                },
                {
                    "owner": "Data Onboarding",
                    "action": "Map",
                    "complete": True,
                    "hashes_match": True,
                },
            ],
        }
    )

    assert result["owner"] == "Data Operations"
    assert "without repeating completed work" in result["action"]


def test_resume_with_both_change_signals_stops_for_operator_disambiguation():
    result = route_next_action(
        {
            "source_configured": True,
            "delivery_changed": True,
            "live_rules_changed": True,
            "resume_phases": [
                {
                    "owner": "Data Profiling",
                    "action": "Keep the verified profile report",
                    "complete": True,
                    "hashes_match": True,
                }
            ],
        }
    )

    assert result["owner"] == "Data Platform"


def test_plan_route_cli_reads_request_file(tmp_path, capsys):
    from edgar_warehouse.cli import main

    request = tmp_path / "route.json"
    request.write_text(
        json.dumps(
            {
                "source_configured": True,
                "delivery_changed": True,
                "live_rules_changed": False,
            }
        )
    )

    assert main(["plan", "route", "--request", str(request)]) == 0
    assert json.loads(capsys.readouterr().out)["owner"] == "Data Operations"


def test_plan_route_cli_accepts_json_on_stdin(monkeypatch, capsys):
    from edgar_warehouse.cli import main

    request = {
        "source_configured": True,
        "delivery_changed": False,
        "live_rules_changed": True,
    }
    monkeypatch.setattr(sys, "stdin", StringIO(json.dumps(request)))

    assert main(["plan", "route", "--request", "-"]) == 0
    assert json.loads(capsys.readouterr().out) == {
        "owner": "Refining Rules",
        "action": "Compare the approved live rules with the changed delivery; do not switch on a rules version.",
    }
