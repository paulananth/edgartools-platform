"""Company mastering ticket 22: data quality before the merge."""

from __future__ import annotations

import copy

import pytest

from edgar_warehouse.mdm.clean import quality
from edgar_warehouse.mdm.clean.adapters import UnsupportedRecord, normalize
from edgar_warehouse.mdm.clean.company_source import CONTRACT, POLICY, SOURCE_CODE
from edgar_warehouse.mdm.clean.matching import _read
from edgar_warehouse.rules import files

PUBLICATION = {"publication_key": "p", "revision": 0, "artifact_sha256": "a" * 64, "member": "m"}


def sec(name="APPLIED MATERIALS INC /DE", state="DC", street="3050 BOWERS AVENUE"):
    return {
        "cik": 6951,
        "entity_name": name,
        "entity_type": "operating",
        "sic": "3674",
        "state_of_incorporation": state,
        "business_address": {
            "street": street,
            "city": "SANTA CLARA",
            "region": "CA",
            "postal_code": "95054-3299",
            "country": "US",
        },
        "last_sync_run_id": "capture-1",
        "last_synced_at": "2026-01-01T00:00:00+00:00",
        "raw_object_id": "raw-6951",
    }


def read(row, contract=CONTRACT):
    return normalize(
        row, source_code=SOURCE_CODE, contract=contract, publication=PUBLICATION, policy=POLICY
    )


class TestTheSecQualityRule:
    def test_dc_is_blanked_then_the_name_tag_fills_the_state(self):
        found = read(sec())
        assert found["fields"]["state_of_incorporation"] == {"op": "value", "value": "DE"}
        fixes = found["provenance"]["quality"]["fixes"]
        assert fixes["dc_state_is_empty"] == {
            "path": "fields.state_of_incorporation",
            "original": "DC",
        }
        assert fixes["state_from_name_tag"]["original"] is None

    def test_dc_without_a_tag_is_unknown_and_the_original_is_kept(self):
        found = read(sec(name="SHELL PLC"))
        assert found["fields"]["state_of_incorporation"] == {"op": "unknown"}
        assert found["provenance"]["quality"]["fixes"]["dc_state_is_empty"]["original"] == "DC"

    @pytest.mark.parametrize("name", ["TOYOTA MOTOR CORP /ADR/", "MERCK & CO INC /NEW/"])
    def test_a_tag_that_is_not_a_us_state_fills_nothing(self, name):
        found = read(sec(name=name, state=None))
        assert found["fields"]["state_of_incorporation"] == {"op": "unknown"}
        assert "state_from_name_tag" not in found["provenance"]["quality"].get("fixes", {})

    def test_a_state_sec_already_gives_is_kept(self):
        found = read(sec(state="CA"))
        assert found["fields"]["state_of_incorporation"] == {"op": "value", "value": "CA"}

    def test_the_standard_address_is_a_matching_copy_and_the_shown_address_is_untouched(self):
        found = read(sec())
        assert found["fields"]["address"]["value"]["street"] == "3050 BOWERS AVENUE"
        assert found["fields"]["address"]["value"]["postcode"] == "95054-3299"
        standard = found["provenance"]["matching"]["address"]
        assert standard["street"] == "3050 BOWERS AVE"
        assert standard["postcode"] == "95054"

    def test_a_registered_agent_address_is_withheld_from_matching(self):
        found = read(sec(street="C/O CORPORATION TRUST CENTER 1209 ORANGE STREET"))
        assert "matching.address" in found["provenance"]["quality"]["withheld"]
        assert _read(found, "matching.address") is None
        assert found["fields"]["address"]["value"]["street"].startswith("C/O")

    def test_a_record_with_no_name_is_rejected_and_blocks(self):
        with pytest.raises(UnsupportedRecord) as caught:
            read(sec(name=""))
        assert caught.value.reason == "quality_name_present"


def block(**changes):
    body = {
        "version": "test-quality-v1",
        "fixes": [],
        "checks": [
            {"id": "street_known", "test": "placeholder@1", "value": "fields.street",
             "on_fail": "flag", "args": {"values": ["NA"]}},
        ],
    }
    body.update(changes)
    return body


class TestTheBlock:
    @pytest.mark.parametrize(
        ("change", "reason"),
        [
            ({"version": ""}, "names its version"),
            ({"extra": 1}, "version, fixes and checks only"),
            ({"checks": [{"id": "x", "test": "nope@1", "value": "fields.a", "on_fail": "flag"}]}, "unknown test"),
            ({"checks": [{"id": "x", "test": "present@1", "value": "fields.a", "on_fail": "drop"}]}, "reject, withhold or flag"),
            ({"checks": [{"id": "x", "test": "present@1", "value": "row.a", "on_fail": "flag"}]}, "reads fields"),
            ({"checks": [{"id": "x", "test": "in_set@1", "value": "fields.a", "on_fail": "flag"}]}, "needs args"),
            ({"fixes": [{"id": "street_known", "fix": "blank_values@1", "args": {"field": "fields.a", "values": []}}]}, "used twice"),
        ],
    )
    def test_a_block_that_cannot_run_is_refused(self, change, reason):
        with pytest.raises(quality.QualityError, match=reason):
            quality.check_quality(block(**change))

    def test_the_repo_quality_rules_are_valid(self):
        for name in ("sec.submissions.company", "gleif"):
            for entry in files.source(name)["mdm"].values():
                if "quality" in entry["contract"]:
                    quality.check_quality(entry["contract"]["quality"])

    def test_a_flag_only_counts(self):
        result = quality.apply(block(), {"street": "N/A"}, {})
        assert result == {"version": "test-quality-v1", "flags": ["street_known"]}

    def test_a_reference_table_is_pinned_by_its_hash(self):
        item = {"id": "state_code_known", "test": "in_reference@1", "value": "fields.state",
                "on_fail": "flag", "args": {"table": "sec-place-codes", "sha256": "0" * 64, "key": "codes"}}
        with pytest.raises(quality.QualityError, match="pinned sha256"):
            quality.apply(block(checks=[item]), {"state": "DE"}, {})

    @pytest.mark.parametrize(
        ("lei", "ok"),
        [("HWUPKR0MPOU8FGXBT394", True), ("HWUPKR0MPOU8FGXBT395", False), ("SHORT", False)],
    )
    def test_the_lei_check_digit(self, lei, ok):
        assert quality.CHECKS["lei_check_digit@1"][0](lei, {}) is ok

    def test_counts_per_fix_and_check(self):
        found = [read(sec()), read(sec(name="SHELL PLC", street="1209 ORANGE STREET"))]
        rejected = [{"reason": "quality_name_present"}, {"reason": "unsupported_identity_kind"}]
        assert quality.counts(found, rejected) == {
            "fixed:dc_state_is_empty": 2,
            "fixed:standard_address": 2,
            "fixed:state_from_name_tag": 1,
            "rejected:name_present": 1,
            "withheld:matching.address": 1,
        }


class TestTheFiles:
    def test_quality_rides_in_the_contract_and_writes_back_to_its_own_file(self, tmp_path):
        body = files.source("sec.submissions.company")
        assert body["mdm"]["sec.submissions.company.v1"]["contract"]["quality"]["version"] == (
            "sec-company-quality-v1"
        )
        files.write_source(body, tmp_path)
        assert (tmp_path / "quality.yaml").exists()
        assert "quality" not in files.load(tmp_path / "source.yaml")["mdm"]["sec.submissions.company.v1"]["contract"]
        assert files.load_source(tmp_path / "source.yaml") == body

    def test_quality_written_inside_the_contract_is_refused(self, tmp_path):
        body = copy.deepcopy(files.source("sec.submissions.company"))
        files.write_source(body, tmp_path)
        text = files.load(tmp_path / "source.yaml")
        text["mdm"]["sec.submissions.company.v1"]["contract"]["quality"] = {"version": "x"}
        (tmp_path / "source.yaml").write_text(files.dumps(text), encoding="utf-8")
        with pytest.raises(files.RulesFileError, match="not in the contract"):
            files.load_source(tmp_path / "source.yaml")

    def test_quality_for_a_contract_the_source_lacks_is_refused(self, tmp_path):
        files.write_source(files.source("gleif"), tmp_path)
        (tmp_path / "quality.yaml").write_text(
            files.dumps({"version": "v", "quality": {"gleif.none.v1": {"checks": []}}}), encoding="utf-8"
        )
        with pytest.raises(files.RulesFileError, match="not a Dataset Contract"):
            files.load_source(tmp_path / "source.yaml")
