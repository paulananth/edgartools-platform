"""Native Company evidence and bounded immutable input preparation."""

import hashlib
import json
from datetime import UTC, datetime

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from edgar_warehouse.mdm.clean.adapters import UnsupportedRecord, normalize
from edgar_warehouse.mdm.clean.company_source import (
    CONTRACT,
    SOURCE_CODE,
    prepare_company_bundle,
)
from edgar_warehouse.mdm.clean.store import Conflict


def source_row(cik, **changes):
    return {
        "cik": cik,
        "entity_name": f"Synthetic Company {cik}",
        "entity_type": "operating",
        "last_sync_run_id": "capture-1",
        "last_synced_at": datetime(2026, 1, 1, tzinfo=UTC),
        "raw_object_id": f"raw-{cik}",
        **changes,
    }


def landing(tmp_path, rows):
    root = tmp_path / "landing"
    root.mkdir()
    pq.write_table(pa.Table.from_pylist(rows), root / "company.parquet")
    manifest = root / "run_manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "target": "silver_landing",
                "run_id": "capture-1",
                "tables": [
                    {
                        "table_name": "sec_company",
                        "relative_path": "company.parquet",
                        "file_count": 1,
                        "row_count": len(rows),
                    }
                ],
            }
        )
    )
    return {
        "landing_root": str(root),
        "landing_manifest": str(manifest),
        "output": str(tmp_path / "pinned"),
        "limit": 1,
        "revision": 0,
        "as_of": "2026-02-01T00:00:00Z",
    }


def test_native_company_kind_identifiers_and_unknown_effective_time():
    publication = {
        "publication_key": "capture-1/company",
        "revision": 0,
        "effective_at": None,
        "artifact_sha256": "a" * 64,
        "member": "records.jsonl",
    }
    row = source_row(123)
    row["last_synced_at"] = row["last_synced_at"].isoformat()
    a = normalize(
        row, source_code=SOURCE_CODE, contract=CONTRACT, publication=publication
    )
    b = normalize(
        {**row, "cik": "0000000123"},
        source_code=SOURCE_CODE,
        contract=CONTRACT,
        publication=publication,
    )
    assert a == b
    assert a["record_key"] == "0000000123" and a["identifiers"] == {"cik": "0000000123"}
    assert a["effective_at"] is None
    assert a["profiles"] == []
    assert a["provenance"]["source"]["observed_at"] == row["last_synced_at"]
    with pytest.raises(UnsupportedRecord, match="unsupported_identity_kind"):
        normalize(
            {**row, "entity_type": "other"},
            source_code=SOURCE_CODE,
            contract=CONTRACT,
            publication=publication,
        )


def test_prepared_bundle_is_bounded_pinned_and_idempotent(tmp_path):
    args = landing(tmp_path, [source_row(123), source_row(456)])
    result = prepare_company_bundle(**args)
    assert result["scope"]["selected_records"] == 1
    assert result["scope"]["available_company_records"] == 2
    assert not result["scope"]["whole_source_complete"]
    output = tmp_path / "pinned"
    for name, info in result["files"].items():
        assert (
            hashlib.sha256((output / name).read_bytes()).hexdigest() == info["sha256"]
        )
    manifest = json.loads((output / "manifest.json").read_text())
    assert manifest["batches"][0]["input"]["record_count"] == 1
    assert "decisions" not in manifest["batches"][0]
    assert "identities" not in manifest["batches"][0]
    assert prepare_company_bundle(**args) == result
    # The same source fact survives a different transport bundle and position.
    larger = tmp_path / "larger"
    prepare_company_bundle(**{**args, "limit": 2, "output": str(larger)})
    assertions = []
    for folder in (output, larger):
        m = json.loads((folder / "manifest.json").read_text())["batches"][0]["input"]
        row = json.loads((folder / "records.jsonl").read_text().splitlines()[0])
        assertions.append(
            normalize(
                row,
                source_code=SOURCE_CODE,
                contract=CONTRACT,
                publication={
                    **m["publication"],
                    "artifact_sha256": m["sha256"],
                    "member": str(folder),
                    "record_locator": str(folder),
                },
            )
        )
    assert assertions[0] == assertions[1]
    (output / "records.jsonl").write_text("corrupted")
    with pytest.raises(Conflict, match="different content"):
        prepare_company_bundle(**args)
    assert (output / "records.jsonl").read_text() == "corrupted"


def test_preparation_rejects_capture_mismatch_and_false_manifest_count(tmp_path):
    args = landing(tmp_path, [source_row(123, last_sync_run_id="other-run")])
    with pytest.raises(Conflict, match="different capture run"):
        prepare_company_bundle(**args)
    from pathlib import Path

    path = Path(args["landing_manifest"])
    body = json.loads(path.read_text())
    body["tables"][0]["row_count"] = 2
    path.write_text(json.dumps(body))
    with pytest.raises(Conflict, match="row count"):
        prepare_company_bundle(**args)
    assert not (tmp_path / "pinned").exists()


def test_a_corrected_reading_of_one_sec_publication_is_a_second_assertion():
    """Company mastering ticket 01, through the real SEC Company contract.

    A mapping correction must not re-bind the record: the subject is keyed on
    source code and record key, and neither moves.
    """
    publication = {
        "publication_key": "capture-1",
        "revision": 0,
        "effective_at": None,
        "artifact_sha256": "a" * 64,
        "member": "company.parquet",
        "record_locator": "line:1",
    }
    # The bundle writer renders source scalars before the adapter sees them.
    row = source_row(
        320193, last_synced_at=datetime(2026, 1, 1, tzinfo=UTC).isoformat()
    )
    first = normalize(
        row, source_code=SOURCE_CODE, contract=CONTRACT, publication=publication
    )
    corrected = normalize(
        row,
        source_code=SOURCE_CODE,
        contract=CONTRACT,
        publication=publication,
        mapping_version=2,
    )
    assert "mapping_version" not in first
    assert corrected["mapping_version"] == 2
    assert corrected["assertion_id"] != first["assertion_id"]
    assert corrected["subject"] == first["subject"]
    assert corrected["record_key"] == first["record_key"]


class TestJurisdictionIsOneFormat:
    """SEC writes "CA"; GLEIF writes "US-CA" (operator, 2026-09-24)."""

    def read(self, state):
        return self.fields(state)["jurisdiction"]

    def fields(self, state):
        return normalize(
            source_row(
                320193,
                state_of_incorporation=state,
                last_synced_at="2026-01-01T00:00:00+00:00",
            ),
            source_code=SOURCE_CODE,
            contract=CONTRACT,
            publication={
                "publication_key": "p",
                "revision": 0,
                "artifact_sha256": "a" * 64,
                "member": "m",
            },
        )["fields"]

    def test_a_us_state_code_becomes_iso_3166_2(self):
        assert self.read("CA") == {"op": "value", "value": "US-CA"}
        assert self.read("dc") == {"op": "value", "value": "US-DC"}

    def test_a_foreign_edgar_code_is_unknown_not_guessed_and_kept_raw(self):
        assert self.read("E9") == {"op": "unknown"}
        assert self.fields("E9")["sec_state_of_incorporation"] == {
            "op": "value",
            "value": "E9",
        }

    def test_an_empty_code_is_unknown(self):
        assert self.read("") == {"op": "unknown"}

    def test_the_company_rule_is_loaded_not_restated(self):
        import json
        from pathlib import Path

        from edgar_warehouse.mdm.clean import company_source

        file = Path(company_source.__file__).parents[1] / "policies" / "company.json"
        assert set(company_source.POLICY["kinds"]) == {"company"}
        assert company_source.POLICY["kinds"]["company"] == json.loads(file.read_text())
        assert company_source.POLICY["kinds"]["company"]["defaults"]["sources"] == [
            "sec.submissions.company.v1",
            "gleif.level1.v1",
        ]
