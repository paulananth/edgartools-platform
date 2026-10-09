"""Caller equivalence against frozen preparation, including physical provenance."""

import json
from pathlib import Path
import pytest
from edgar_warehouse.mdm.clean.company_prepare import prepare_company_bundle
from tests.support.retired_company_preparation import (
    prepare_company_bundle as historical,
)
from tests.mdm.test_clean_company_source import (
    landing,
    source_row,
    ticker_row,
    filing_row,
    address_row,
)


@pytest.mark.parametrize("limit", [1, 2])
def test_preparation_preserves_records_publication_scope_and_all_original_files(
    tmp_path, limit
):
    args = landing(
        tmp_path,
        [source_row(123), source_row(456, entity_type="other")],
        tickers=[
            ticker_row(123, "B", source_rank=2),
            ticker_row(123, "A"),
            ticker_row(123, "A", source_rank=3),
        ],
        filings=[
            filing_row(123, "10-Q"),
            filing_row(123, "10-K"),
            filing_row(123, "10-K"),
        ],
        addresses=[
            address_row(123, street1="first"),
            address_row(123, address_type="mailing"),
            address_row(123, street1="last"),
        ],
    )
    args["limit"] = limit
    expected = historical(**{**args, "output": str(tmp_path / "historical")})
    actual = prepare_company_bundle(**args)
    for name in expected["files"]:
        assert (tmp_path / "historical" / name).read_bytes() == (
            Path(args["output"]) / name
        ).read_bytes(), name
    assert actual["scope"] == expected["scope"]
    assert prepare_company_bundle(**args) == actual
    records = [
        json.loads(line)
        for line in (Path(args["output"]) / "records.jsonl").read_text().splitlines()
    ]
    assert records[0]["forms"] == ["10-K", "10-Q"]
    assert records[0]["tickers"] == ["A", "B"]
    assert records[0]["business_address"]["street"] == "last"


def test_large_bronze_inventory_preserves_selected_provenance_and_refusals(tmp_path):
    from edgar_warehouse.mdm.clean.company_source import bronze_receipts
    from edgar_warehouse.mdm.clean.company_prepare import verify_company_bundle
    from edgar_warehouse.mdm.clean.store import Conflict

    selected = "a" * 64
    args = landing(tmp_path, [source_row(123, raw_object_id=selected)])
    body = bronze_receipts(
        "capture-1",
        [{"sha256": f"{n:064x}", "path": f"s3://bronze/{n}.json"}
         for n in range(10001)]
        + [{"sha256": selected, "path": "s3://bronze/selected.json"}],
    )
    path = tmp_path / "receipts.json"
    path.write_text(json.dumps(body))
    args["bronze_receipts_path"] = str(path)
    expected = historical(**{**args, "output": str(tmp_path / "historical")})
    actual = prepare_company_bundle(**args)
    for name in expected["files"]:
        assert (tmp_path / "historical" / name).read_bytes() == (
            Path(args["output"]) / name
        ).read_bytes(), name
    assert verify_company_bundle(args["output"], expected=actual)["records"] == 1
    assert prepare_company_bundle(**args) == actual

    # Even an unrelated malformed receipt must still be refused before selection.
    body["receipts"][0]["object"] = ""
    path.write_text(json.dumps(body))
    for prepare in (historical, prepare_company_bundle):
        with pytest.raises(Conflict, match="names no object"):
            prepare(**args)


def test_active_cli_has_no_retired_preparation_import():
    import inspect
    from edgar_warehouse.mdm.clean import cli, company_source

    assert ".company_prepare import prepare_company_bundle" in inspect.getsource(
        cli.prepare_clean_company
    )
    for name in (
        "prepare_company_bundle",
        "_filed_forms",
        "_catalog_tickers",
        "_census_evidence",
        "_pin_evidence",
    ):
        assert not hasattr(company_source, name), name
    assert callable(company_source.write_name_census)


@pytest.mark.parametrize(
    "member",
    [
        "records.jsonl",
        "workers/main.input",
        "workers/forms.reading.json",
        "workers/proof.json",
        "name-census.json",
        "manifest.json",
    ],
)
def test_published_proof_replay_and_corruption_refusal(tmp_path, member):
    from edgar_warehouse.mdm.clean.company_prepare import verify_company_bundle
    from edgar_warehouse.mdm.clean.store import Conflict

    args = landing(tmp_path, [source_row(123)])
    report = prepare_company_bundle(**args)
    assert verify_company_bundle(args["output"], expected=report) == {
        "source.output": True,
        "source.combined": True,
        "records": 1,
    }
    path = Path(args["output"]) / member
    path.write_bytes(b"corrupted")
    with pytest.raises(Conflict, match="differs"):
        verify_company_bundle(args["output"], expected=report)
    with pytest.raises(Conflict, match="different content"):
        prepare_company_bundle(**args)


def test_blank_tickers_with_no_rank_preserve_historical_skip(tmp_path):
    args = landing(
        tmp_path,
        [source_row(123)],
        tickers=[ticker_row(123, "", source_rank=None), ticker_row(123, "A")],
    )
    historical(**{**args, "output": str(tmp_path / "historical")})
    prepare_company_bundle(**args)
    assert (tmp_path / "historical/records.jsonl").read_bytes() == (
        Path(args["output"]) / "records.jsonl"
    ).read_bytes()


def test_more_than_one_hundred_thousand_filing_rows_preserve_parity(tmp_path):
    args = landing(
        tmp_path, [source_row(123)], filings=[filing_row(123, "10-K")] * 100001
    )
    historical(**{**args, "output": str(tmp_path / "historical")})
    prepare_company_bundle(**args)
    assert (tmp_path / "historical/records.jsonl").read_bytes() == (
        Path(args["output"]) / "records.jsonl"
    ).read_bytes()


def test_large_frozen_census_does_not_make_selected_company_unbounded(tmp_path):
    args = landing(tmp_path, [source_row(123)])
    path = Path(args["name_census"])
    census = json.loads(path.read_bytes())
    census["entries"].update(
        {f"UNRELATED {n}": {"ciks": [], "leis": []} for n in range(100001)}
    )
    path.write_text(json.dumps(census))
    historical(**{**args, "output": str(tmp_path / "historical")})
    prepare_company_bundle(**args)
    assert (tmp_path / "historical/records.jsonl").read_bytes() == (
        Path(args["output"]) / "records.jsonl"
    ).read_bytes()


@pytest.mark.parametrize("fault", ["forms", "tickers", "name_key", "bronze"])
def test_configuration_fault_is_observable_at_active_caller(
    tmp_path, monkeypatch, fault
):
    from copy import deepcopy
    from edgar_warehouse.mdm.clean import company_prepare

    args = landing(
        tmp_path,
        [source_row(123, raw_object_id="a" * 64)],
        tickers=[ticker_row(123, "A")],
        filings=[filing_row(123, "10-K")],
    )
    if fault == "bronze":
        from edgar_warehouse.mdm.clean.company_source import bronze_receipts

        receipts = tmp_path / "receipts.json"
        receipts.write_text(
            json.dumps(
                bronze_receipts(
                    "capture-1",
                    [{"sha256": "a" * 64, "path": "s3://bronze/example.json"}],
                )
            )
        )
        args["bronze_receipts_path"] = str(receipts)
    historical(**{**args, "output": str(tmp_path / "historical")})
    load = company_prepare.rules_files.load

    def damaged(path):
        body = deepcopy(load(path))
        if Path(path).name == "combine-landed.yaml" and fault in ("forms", "tickers"):
            body["combine"]["groups"][fault]["where"] = {"cik": 999}
        elif Path(path).name == "landed-preparation.yaml":
            if fault == "name_key":
                body["company"]["read"]["tables"]["company"]["columns"]["_name_key"] = {
                    "const": {"value": "WRONG"}
                }
            elif fault == "bronze":
                body["company"]["read"]["tables"]["company"]["columns"]["_origin"][
                    "object"
                ]["fields"]["bronze"] = {"const": {"value": None}}
        return body

    monkeypatch.setattr(company_prepare.rules_files, "load", damaged)
    prepare_company_bundle(**args)
    assert (tmp_path / "historical/records.jsonl").read_bytes() != (
        Path(args["output"]) / "records.jsonl"
    ).read_bytes()


def test_late_foreign_run_cannot_hide_behind_duplicate_framing(tmp_path):
    from edgar_warehouse.mdm.clean.store import Conflict

    args = landing(
        tmp_path,
        [source_row(123)],
        filings=[filing_row(123, "10-K")] * 100001
        + [filing_row(None, "10-K", last_sync_run_id="stale")],
    )
    with pytest.raises(Conflict, match="different capture run"):
        historical(**{**args, "output": str(tmp_path / "historical")})
    with pytest.raises(Conflict, match="different capture run"):
        prepare_company_bundle(**args)
    assert not Path(args["output"]).exists()
