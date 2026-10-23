"""Invented record vocabulary reaches the normal native comparison facade."""

import copy
import os
import shutil
import subprocess
import sys

import pytest

from edgar_warehouse.mdm.clean import catalog
from edgar_warehouse.rules import files


@pytest.fixture
def configured_root(tmp_path):
    shutil.copytree(files.ROOT, tmp_path, dirs_exist_ok=True)
    body = copy.deepcopy(catalog.CATALOG)
    body["kinds"].append("invented-kind")
    body["legacy_pair_comparison"] = "invented-comparison"
    body["pair_comparisons"]["invented-comparison"] = {
        "name_field": "invented_name",
        "identifier_namespace": "invented_reference",
        "census_field": "invented_census",
        "census_entries_field": "invented_matches",
        "census_holder_keys_field": "invented_keys",
        "census_holder_count_field": "invented_key_count",
        "census_identifier_count_field": "invented_match_count",
        "census_other_holders_field": "invented_other_count",
        "cascade_field": "invented_assignment",
        "cascade_identifier_field": "invented_target",
        "eligibility_kind": "invented-kind",
        "eligibility_categories": ["INVENTED"],
        "status_field": "matching.invented_status",
        "registration_status_field": "invented_registration",
        "left_address_fields": ["invented_location"],
        "right_address_fields": ["invented_preferred", "invented_fallback"],
    }
    (tmp_path / catalog.RELATIVE).write_text(files.dumps(body))
    return tmp_path


PROGRAM = '''
import copy
from edgar_warehouse.mdm.clean.matching import compare_candidate_records
from edgar_warehouse.mdm.clean.name_census import VERSION
from edgar_warehouse.mdm.clean.cascade import VERSION as CASCADE
from edgar_warehouse.mdm.clean.store import Conflict

def field(value): return {"op": "value", "value": value}
place = {"street": "1 INVENTED WAY", "city": "EXAMPLE", "postcode": "11111", "country": "ZZ"}
entry = {"version": VERSION, "key": "INVENTED LAB INC", "invented_keys": ["origin-1"],
         "invented_key_count": 1, "invented_matches": [["target-1", "2026-01-01T00:00:00Z"]],
         "invented_match_count": 1, "invented_other_count": 0,
         "invented_assignment": {"version": CASCADE, "pass": "P1", "invented_target": "target-1",
             "last_update": "2026-01-01T00:00:00Z", "key": "INVENTED LAB INC", "flags": [], "via": "legal name"}}
left = {"record_key": "origin-1", "fields": {"invented_name": field("INVENTED LAB INC")},
        "provenance": {"matching": {"invented_census": entry, "invented_location": place}}}
right = {"kind": "invented-kind", "identifiers": {"invented_reference": "target-1"},
         "effective_at": "2026-01-01T00:00:00Z",
         "fields": {"invented_name": field("INVENTED LAB INC"), "invented_registration": field("ISSUED")},
         "provenance": {"matching": {"invented_status": "ACCEPTED", "invented_preferred": place}}}
names = {"sec_normalizer": "normalize_text@legal-form-kept-v1", "gleif_normalizer": "normalize_text@legal-form-kept-v1"}
eligibility = {"categories": ["INVENTED"], "entity_statuses": ["ACCEPTED"],
               "refused_registration_statuses": ["REFUSED"]}
def compare(primitive, args):
    return compare_candidate_records({"when": [{"primitive": primitive, "args": args}]}, [(left, right)])
def census(): return compare("name_census_match@1", names)
def eligible(): return compare("gleif_entity_eligible@1", eligibility)
def cascade(): return compare("cascade_pass@1", {**names, "pass": "P1", "compare": ["street", "city", "postcode"], "refused_flags": []})
'''


SCENARIOS = {
    "census": 'assert census() == [[True, False]]',
    "census_wrong_namespace": 'right["identifiers"] = {"other": "target-1"}; assert census() == [[False, False]]',
    "census_ambiguous": 'entry["invented_matches"] *= 2; assert census() == [[False, False]]',
    "census_stale_version": 'right["effective_at"] = "2026-02-01T00:00:00Z"; assert census() == [[False, False]]',
    "census_withheld_name": 'left["provenance"]["quality"] = {"withheld": ["fields.invented_name"]}; assert census() == [[False, False]]',
    "eligibility": 'assert eligible() == [[True, False]]',
    "eligibility_wrong_kind": 'right["kind"] = "other-kind"; assert eligible() == [[False, False]]',
    "eligibility_refused": 'right["fields"]["invented_registration"] = field("REFUSED"); assert eligible() == [[False, False]]',
    "eligibility_missing_status": 'del right["provenance"]["matching"]["invented_status"]; assert eligible() == [[False, False]]',
    "eligibility_withheld_status": 'right["provenance"]["quality"] = {"withheld": ["matching.invented_status"]}; assert eligible() == [[False, False]]',
    "cascade": 'assert cascade() == [[True, False]]',
    "cascade_mismatch": 'right["provenance"]["matching"]["invented_preferred"] = {**place, "street": "2 ELSEWHERE"}; assert cascade() == [[False, False]]',
    "cascade_fallback": 'del right["provenance"]["matching"]["invented_preferred"]; right["provenance"]["matching"]["invented_fallback"] = place; assert cascade() == [[True, False]]',
    "cascade_stale_version": 'right["effective_at"] = "2026-02-01T00:00:00Z"; assert cascade() == [[False, False]]',
    "unknown_profile": '''
try:
    compare_candidate_records({"pair_comparison": "absent-profile", "when": []}, [(left, right)])
except Conflict:
    pass
else:
    raise AssertionError("Unknown comparison profile was accepted")
''',
}


@pytest.mark.parametrize("scenario", SCENARIOS)
def test_configured_record_shape_reaches_normal_comparison(configured_root, scenario):
    result = subprocess.run(
        [sys.executable, "-c", PROGRAM + "\n" + SCENARIOS[scenario]],
        env={**os.environ, "EDGAR_RULES_ROOT": str(configured_root)},
        capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == 0, result.stderr


def test_rule_selects_another_profile_without_changing_the_legacy_default(configured_root):
    body = files.load(configured_root / catalog.RELATIVE)
    body["legacy_pair_comparison"] = "existing-name-binding"
    (configured_root / catalog.RELATIVE).write_text(files.dumps(body))
    program = PROGRAM + '''
def compare(primitive, args):
    return compare_candidate_records({"pair_comparison": "invented-comparison",
        "when": [{"primitive": primitive, "args": args}]}, [(left, right)])
assert census() == [[True, False]]
assert eligible() == [[True, False]]
assert cascade() == [[True, False]]
from edgar_warehouse.mdm.clean.activation import check_name_binding_rule
rule = {"rule_id": "invented-rule", "pair_comparison": "invented-comparison",
    "applies_to_verdict": "invented-kind", "emits": ["bind"], "on_no_match": "wait",
    "source": "invented-right", "holder_source": "invented-left", "when": [
        {"primitive": "name_census_match@1", "args": names},
        {"primitive": "postal_agrees@1", "args": {}}]}
check_name_binding_rule("invented-kind", rule, {})
for changed in ({**rule, "pair_comparison": "missing"},
                {**rule, "pair_comparison": "existing-name-binding"}):
    try:
        check_name_binding_rule("invented-kind", changed, {})
    except Conflict:
        pass
    else:
        raise AssertionError("Invalid comparison profile passed registration checks")
'''
    result = subprocess.run([sys.executable, "-c", program],
        env={**os.environ, "EDGAR_RULES_ROOT": str(configured_root)},
        capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize("key,value", [
    ("eligibility_kind", "unconfigured-kind"), ("name_field", ""),
    ("left_address_fields", []), ("right_address_fields", ["duplicate", "duplicate"]),
    ("eligibility_categories", [None]), ("identifier_namespace", False),
])
def test_invalid_comparison_configuration_is_refused(configured_root, key, value):
    body = files.load(configured_root / catalog.RELATIVE)
    body["pair_comparisons"]["invented-comparison"][key] = value
    (configured_root / catalog.RELATIVE).write_text(files.dumps(body))
    with pytest.raises(ValueError, match="pair comparison"):
        catalog.load(configured_root)
