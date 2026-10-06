"""The data-quality skill's helper: findings → a quality block the engine loads, measured on records."""

import sys
from pathlib import Path

import pytest
import yaml

from edgar_warehouse.mdm.clean import quality

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "skills" / "data-quality" / "scripts"))
import quality_plan  # noqa: E402


def _findings():
    items = [
        {"check": "missing", "column": "id", "rows": 1, "examples": [], "args": {}, "proposal": "exception"},
        {"check": "placeholder", "column": "note", "rows": 2, "examples": ["N/A"],
         "args": {"values": ["NA", "NONE"]}, "proposal": "withhold"},
        {"check": "shape_outlier", "column": "ref", "rows": 1, "examples": ["A7"],
         "args": {"regex": "[A-Z][A-Z][0-9][0-9]"}, "proposal": "flag"},
        {"check": "code_list", "column": "status", "rows": 0, "examples": [],
         "args": {"values": ["held", "open"]}, "proposal": "flag"},
        {"check": "check_digit", "column": "ref", "rows": 1, "examples": [], "args": {"family": "luhn"},
         "proposal": "withhold"},
        {"check": "link_not_found", "column": "owner", "rows": 3, "examples": [], "args": {}, "proposal": "flag"},
        {"check": "hierarchy_invalid", "column": "up", "rows": 2, "examples": [], "args": {}, "proposal": "flag"},
    ]
    return {"approval": {"status": "approved"}, "parts": [{"part": "acct", "quality": items}]}


FIELDS = {"id": "fields.id", "note": "fields.note", "ref": "fields.reference", "status": "fields.status"}
RECORDS = [{"id": None, "note": "x", "ref": "AB12", "status": "open"},
           {"id": "2", "note": "N/A", "ref": "AB13", "status": "held"},
           {"id": "3", "note": "none", "ref": "A7", "status": "open"},
           {"id": "4", "note": None, "ref": "AB14", "status": None}]


def test_every_target_in_the_catalog_is_an_engine_check():
    for target in quality_plan.CATALOG.values():
        assert target["test"] in quality.CHECKS


def test_draft_maps_findings_onto_engine_checks_and_lists_new_code():
    plan = quality_plan.draft(_findings(), "acct", FIELDS, "acct-quality-v1")
    quality.check_quality(plan["block"])  # the engine itself refuses anything it could not run
    tests = {c["id"]: (c["test"], c["value"], c["on_fail"]) for c in plan["block"]["checks"]}
    assert tests == {"missing_id": ("present@1", "fields.id", "exception"),
                     "placeholder_note": ("placeholder@1", "fields.note", "withhold"),
                     "shape_outlier_reference": ("pattern@1", "fields.reference", "flag"),
                     "code_list_status": ("in_set@1", "fields.status", "flag")}
    assert {(i["check"], i["column"]) for i in plan["new_code"]} == {
        ("check_digit", "ref"), ("link_not_found", "owner"), ("hierarchy_invalid", "up")}
    assert plan["expected"] == {"missing_id": 1, "placeholder_note": 2, "shape_outlier_reference": 1,
                                "code_list_status": 0}


def test_a_check_digit_maps_only_where_the_engine_test_fits():
    findings = _findings()
    findings["parts"][0]["quality"] = [{"check": "check_digit", "column": "ref", "rows": 1, "examples": [],
                                        "args": {"family": "mod97_10", "length": 20}, "proposal": "withhold"}]
    plan = quality_plan.draft(findings, "acct", FIELDS, "v1")
    assert [c["test"] for c in plan["block"]["checks"]] == ["lei_check_digit@1"] and not plan["new_code"]
    findings["parts"][0]["quality"][0]["args"]["length"] = 18
    assert quality_plan.draft(findings, "acct", FIELDS, "v1")["new_code"]


def test_a_column_with_no_field_is_listed_not_guessed():
    plan = quality_plan.draft(_findings(), "acct", {"id": "fields.id"}, "v1")
    assert [c["id"] for c in plan["block"]["checks"]] == ["missing_id"]
    assert {i["column"] for i in plan["unmapped"]} == {"note", "ref", "status"}


def test_draft_refuses_findings_that_are_not_approved():
    findings = _findings()
    findings["approval"]["status"] = "draft"
    with pytest.raises(quality_plan.PlanError, match="not approved"):
        quality_plan.draft(findings, "acct", FIELDS, "v1")


def test_measure_counts_equal_profiling_and_each_planted_record_fires():
    plan = quality_plan.draft(_findings(), "acct", FIELDS, "acct-quality-v1")
    records = [quality_plan.mapped(row, FIELDS) for row in RECORDS]
    measured = quality_plan.measure(plan["block"], records)
    assert measured == plan["expected"]
    assert quality_plan.planted_fire(plan["block"]) == {c["id"]: True for c in plan["block"]["checks"]}


def test_write_gives_the_source_file_shape(tmp_path):
    plan = quality_plan.draft(_findings(), "acct", FIELDS, "acct-quality-v1")
    path = quality_plan.write(plan, "acct_code", tmp_path / "quality.yaml")
    body = yaml.safe_load(path.read_text())
    assert body["version"] == "acct-quality-v1" and set(body["quality"]) == {"acct_code"}
    quality.check_quality({"version": body["version"], **body["quality"]["acct_code"]})
