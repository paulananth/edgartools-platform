"""Native Company evidence and bounded immutable input preparation."""

import copy
import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from edgar_warehouse.mdm.clean.adapters import UnsupportedRecord
from edgar_warehouse.mdm.clean.adapters import normalize as _normalize
from edgar_warehouse.mdm.clean.company_source import (
    CONTRACT,
    POLICY,
    SOURCE_CODE,
    prepare_company_bundle,
)
from edgar_warehouse.mdm.clean.store import Conflict
from tests.mdm.test_clean_activation import proof

# Field and identity tests need an active rule; this synthetic proof belongs
# only to the fixture. The standard POLICY deliberately stays inactive.
TEST_POLICY = copy.deepcopy(POLICY)
TEST_POLICY["automatic_rules"] = [
    {
        "kind": "company",
        "family": "classification",
        "rule_id": "sec-company-candidate",
        "rule_version": "2026-09-24.8",
        "verdict": "company",
        "activation": "measured",
        "proof": proof(),
    }
]


def normalize(row, **kwargs):
    return _normalize(row, policy=TEST_POLICY, **kwargs)


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


def ticker_row(cik, ticker, **changes):
    return {
        "cik": cik,
        "ticker": ticker,
        "exchange": "Nasdaq",
        "source_name": "company_tickers_exchange",
        "source_rank": 1,
        "last_sync_run_id": "catalog-1",
        "last_synced_at": datetime(2026, 1, 2, tzinfo=UTC),
        **changes,
    }


def write_member(root, run_id, table_name, rows):
    """One landing run: its parquet member and the manifest that names it."""
    pq.write_table(pa.Table.from_pylist(rows), root / f"{table_name}.parquet")
    manifest = root / f"{run_id}.json"
    manifest.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "target": "silver_landing",
                "run_id": run_id,
                "tables": [
                    {
                        "table_name": table_name,
                        "relative_path": f"{table_name}.parquet",
                        "file_count": 1,
                        "row_count": len(rows),
                    }
                ],
            }
        )
    )
    return manifest


def landing(tmp_path, rows, tickers=None):
    root = tmp_path / "landing"
    root.mkdir(parents=True)
    manifest = write_member(root, "capture-1", "sec_company", rows)
    # By default the catalog lists only a filer outside the sample.
    ticker_manifest = write_member(
        root, "catalog-1", "sec_company_ticker", tickers or [ticker_row(999, "ZZZ")]
    )
    return {
        "landing_root": str(root),
        "landing_manifest": str(manifest),
        "ticker_manifest": str(ticker_manifest),
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
    with pytest.raises(UnsupportedRecord, match="classification_deferred"):
        normalize(
            {**row, "entity_type": "other"},
            source_code=SOURCE_CODE,
            contract=CONTRACT,
            publication=publication,
        )


def test_step_four_requires_the_landing_filer_category():
    publication = {
        "publication_key": "capture-1/company",
        "revision": 0,
        "effective_at": None,
        "artifact_sha256": "a" * 64,
        "member": "records.jsonl",
    }
    row = source_row(
        1306965,
        entity_name="Shell plc",
        entity_type="other",
        sic="1311",
        category="",
    )
    row["last_synced_at"] = row["last_synced_at"].isoformat()
    for missing in ("", None):
        with pytest.raises(
            UnsupportedRecord, match="classification_deferred"
        ) as caught:
            normalize(
                {**row, "category": missing},
                source_code=SOURCE_CODE,
                contract=CONTRACT,
                publication=publication,
            )
        assert caught.value.detail["classification"]["step"] == "5"
    body = normalize(
        {**row, "category": "Large accelerated filer"},
        source_code=SOURCE_CODE,
        contract=CONTRACT,
        publication=publication,
    )
    assert body["provenance"]["classification"]["step"] == "4"


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


class TestTheCompanyRule:
    """SEC gives state of incorporation; GLEIF gives jurisdiction (2026-09-24)."""

    def test_sec_state_of_incorporation_is_its_own_field_as_sec_writes_it(self):
        fields = normalize(
            source_row(
                1306965,
                state_of_incorporation="DC",
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
        assert fields["state_of_incorporation"] == {"op": "value", "value": "DC"}
        assert "jurisdiction" not in fields

    def test_blank_text_is_unknown_not_a_value(self):
        fields = normalize(
            source_row(
                937966,
                state_of_incorporation="",
                description="   ",
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
        assert fields["state_of_incorporation"] == {"op": "unknown"}
        assert fields["description"] == {"op": "unknown"}

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


class TestTickersComeFromTheCatalog:
    """SEC's ticker catalog is its own landing run, pinned beside the Company one.

    The landing Company row carries no ticker, and the rule needs one to hold
    back a filer with no listing (ticket 12, option 1).
    """

    def records(self, args):
        prepare_company_bundle(**args)
        text = (Path(args["output"]) / "records.jsonl").read_text()
        return [json.loads(line) for line in text.splitlines()]

    def test_each_filer_gets_its_catalog_tickers_in_rank_order(self, tmp_path):
        args = landing(
            tmp_path,
            [source_row(123), source_row(456)],
            [
                ticker_row(123, "BRKB", source_rank=2),
                ticker_row(123, "BRKA", source_rank=1),
            ],
        )
        rows = self.records({**args, "limit": 2})
        assert [r["tickers"] for r in rows] == [["BRKA", "BRKB"], []]

    def test_the_catalog_member_is_pinned_in_every_record_and_the_key(self, tmp_path):
        args = landing(tmp_path, [source_row(123)], [ticker_row(123, "AAPL")])
        prepare_company_bundle(**args)
        out = Path(args["output"])
        pinned = hashlib.sha256((out / "tickers.parquet").read_bytes()).hexdigest()
        origin = json.loads((out / "records.jsonl").read_text())["_origin"]
        assert origin["tickers"]["sha256"] == pinned
        assert origin["tickers"]["run_id"] == "catalog-1"
        key = json.loads((out / "manifest.json").read_text())["batches"][0]["input"][
            "publication"
        ]["publication_key"]
        assert key.endswith(f":sec_company_ticker:{pinned}")

    def test_a_different_catalog_is_a_different_publication(self, tmp_path):
        first = landing(tmp_path / "a", [source_row(123)], [ticker_row(123, "AAPL")])
        second = landing(tmp_path / "b", [source_row(123)], [ticker_row(123, "AAPX")])

        def key(args):
            prepare_company_bundle(**args)
            body = json.loads((Path(args["output"]) / "manifest.json").read_text())
            return body["batches"][0]["input"]["publication"]["publication_key"]

        assert key(first) != key(second)

    def test_a_catalog_row_from_another_run_is_refused(self, tmp_path):
        args = landing(
            tmp_path,
            [source_row(123)],
            [ticker_row(123, "AAPL", last_sync_run_id="catalog-0")],
        )
        with pytest.raises(Conflict, match="different catalog run"):
            prepare_company_bundle(**args)

    def test_a_ticker_manifest_without_the_catalog_member_is_refused(self, tmp_path):
        args = landing(tmp_path, [source_row(123)])
        body = json.loads(Path(args["ticker_manifest"]).read_text())
        body["tables"][0]["table_name"] = "sec_company_address"
        Path(args["ticker_manifest"]).write_text(json.dumps(body))
        with pytest.raises(ValueError, match="sec_company_ticker"):
            prepare_company_bundle(**args)

    def test_a_ticker_manifest_outside_the_root_is_refused(self, tmp_path):
        args = landing(tmp_path, [source_row(123)])
        outside = tmp_path / "elsewhere.json"
        outside.write_text(Path(args["ticker_manifest"]).read_text())
        with pytest.raises(ValueError, match="inside its root"):
            prepare_company_bundle(**{**args, "ticker_manifest": str(outside)})
