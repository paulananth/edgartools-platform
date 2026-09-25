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
    write_name_census,
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
        "rule_version": "2026-09-25.13",
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
        "sic": "1234",
        "tickers": ["SYN"],
        "forms": ["10-K"],
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


def filing_row(cik, form, **changes):
    return {
        "accession_number": f"{cik}-{form}",
        "cik": cik,
        "form": form,
        "last_sync_run_id": "capture-1",
        "last_synced_at": datetime(2026, 1, 1, tzinfo=UTC),
        **changes,
    }


def address_row(cik, **changes):
    return {
        "cik": cik,
        "address_type": "business",
        "street1": "1 Main Street",
        "street2": None,
        "city": "Cupertino",
        "state_or_country": "CA",
        "zip_code": "95014",
        "country": "CA",
        "last_sync_run_id": "capture-1",
        "last_synced_at": datetime(2026, 1, 1, tzinfo=UTC),
        **changes,
    }


def former_row(cik, name, **changes):
    return {
        "cik": cik,
        "former_name": name,
        "date_changed": None,
        "ordinal": 1,
        "last_sync_run_id": "capture-1",
        **changes,
    }


def gleif_archive(tmp_path, records=()):
    """A full GLEIF Golden Copy archive and its verified metadata, for the census."""
    import io
    import zipfile

    raw = io.BytesIO()
    with zipfile.ZipFile(raw, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("golden.json", json.dumps({"records": list(records)}))
    archive = tmp_path / "gleif-level1.json.zip"
    archive.write_bytes(raw.getvalue())
    metadata = tmp_path / "gleif-level1.metadata.json"
    metadata.write_text(
        json.dumps(
            {
                "format": "json.zip",
                "cdf_version": "LEI_3.1",
                "content_date": "2026-09-11T16:00:00+00:00",
                "file_content": "GLEIF_FULL_PUBLISHED",
                "delta_start": None,
                "record_count": len(records),
            }
        )
    )
    return archive, metadata, hashlib.sha256(raw.getvalue()).hexdigest()


def write_run(root, run_id, tables):
    """One landing run: a parquet member per table and the manifest naming them."""
    for table_name, rows in tables.items():
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
                    for table_name, rows in tables.items()
                ],
            }
        )
    )
    return manifest


def raw_object_row(cik, **changes):
    return {
        "raw_object_id": f"raw-{cik}",
        "source_type": "submissions",
        "cik": cik,
        "storage_path": f"bronze/submissions/cik={cik}/CIK{cik:010d}.json",
        "sha256": hashlib.sha256(str(cik).encode()).hexdigest(),
        **changes,
    }


def landing(
    tmp_path,
    rows,
    tickers=None,
    filings=None,
    addresses=None,
    former=None,
    gleif=(),
    raw_objects=None,
):
    root = tmp_path / "landing"
    root.mkdir(parents=True)
    # By default the filing list, the addresses, the former names and the
    # catalog name only a filer outside the sample.
    manifest = write_run(
        root,
        "capture-1",
        {
            "sec_company": rows,
            "sec_company_filing": filings or [filing_row(999, "10-K")],
            "sec_company_address": addresses or [address_row(999)],
            "sec_company_former_name": former or [former_row(999, "OLD NAME INC")],
            **({"sec_raw_object": raw_objects} if raw_objects is not None else {}),
        },
    )
    ticker_manifest = write_run(
        root,
        "catalog-1",
        {"sec_company_ticker": tickers or [ticker_row(999, "ZZZ")]},
    )
    archive, metadata, sha = gleif_archive(tmp_path, gleif)
    census = tmp_path / "name-census.json"
    write_name_census(
        landing_root=str(root),
        landing_manifest=str(manifest),
        gleif_archive=str(archive),
        gleif_metadata=str(metadata),
        gleif_sha256=sha,
        output=str(census),
    )
    return {
        "landing_root": str(root),
        "landing_manifest": str(manifest),
        "ticker_manifest": str(ticker_manifest),
        "name_census": str(census),
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


def test_step_ten_requires_the_landing_filer_category():
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
        assert caught.value.detail["classification"]["step"] == "11"
    body = normalize(
        {**row, "category": "Large accelerated filer"},
        source_code=SOURCE_CODE,
        contract=CONTRACT,
        publication=publication,
    )
    assert body["provenance"]["classification"]["step"] == "10"


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
    # The Name Census reads the whole capture first and refuses it already.
    with pytest.raises(Conflict, match="different capture run"):
        landing(tmp_path / "a", [source_row(123, last_sync_run_id="other-run")])
    args = landing(tmp_path, [source_row(123)])
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
        assert f":sec_company_ticker:{pinned}:name_census:" in key

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


class TestFormsComeFromTheFilingList:
    """The forms a filer files, from the same capture as its Company row.

    The Forms hold-back reads them: a Form 10 with a Form D and no BDC
    election, or a registered fund's reports, holds a record back (ticket 12).
    """

    def records(self, args):
        prepare_company_bundle(**args)
        text = (Path(args["output"]) / "records.jsonl").read_text()
        return [json.loads(line) for line in text.splitlines()]

    def test_each_filer_gets_its_distinct_forms(self, tmp_path):
        args = landing(
            tmp_path,
            [source_row(123), source_row(456)],
            filings=[
                filing_row(123, "10-K"),
                filing_row(123, "D", accession_number="a2"),
                filing_row(123, "10-K", accession_number="a3"),
            ],
        )
        rows = self.records({**args, "limit": 2})
        assert [r["forms"] for r in rows] == [["10-K", "D"], []]

    def test_the_filing_member_is_pinned_in_every_record_and_the_key(self, tmp_path):
        args = landing(tmp_path, [source_row(123)], filings=[filing_row(123, "D")])
        prepare_company_bundle(**args)
        out = Path(args["output"])
        pinned = hashlib.sha256((out / "filings.parquet").read_bytes()).hexdigest()
        origin = json.loads((out / "records.jsonl").read_text())["_origin"]
        assert origin["forms"]["sha256"] == pinned
        assert origin["forms"]["run_id"] == "capture-1"
        key = json.loads((out / "manifest.json").read_text())["batches"][0]["input"][
            "publication"
        ]["publication_key"]
        assert f":capture-1:sec_company_filing:{pinned}:" in key

    def test_a_filing_row_from_another_run_is_refused(self, tmp_path):
        args = landing(
            tmp_path,
            [source_row(123)],
            filings=[filing_row(123, "D", last_sync_run_id="capture-0")],
        )
        with pytest.raises(Conflict, match="different capture run"):
            prepare_company_bundle(**args)

    def test_a_capture_without_the_filing_member_is_refused(self, tmp_path):
        args = landing(tmp_path, [source_row(123)])
        body = json.loads(Path(args["landing_manifest"]).read_text())
        body["tables"] = [t for t in body["tables"] if t["table_name"] == "sec_company"]
        Path(args["landing_manifest"]).write_text(json.dumps(body))
        with pytest.raises(ValueError, match="sec_company_filing"):
            prepare_company_bundle(**args)


class TestMatchingEvidenceIsPinned:
    """Ticket 08: the business address and the Name Census beside every record."""

    def test_the_business_address_and_census_entry_travel_with_the_record(
        self, tmp_path
    ):
        args = landing(
            tmp_path,
            [source_row(320193, entity_name="APPLE INC")],
            addresses=[
                address_row(320193),
                address_row(320193, address_type="mailing", zip_code="00000"),
            ],
            gleif=[
                {
                    "LEI": {"$": "HWUPKR0MPOU8FGXBT394"},
                    "Entity": {
                        "LegalName": {"$": "Apple Inc."},
                        "EntityCategory": {"$": "GENERAL"},
                    },
                    "Registration": {"LastUpdateDate": {"$": "2026-09-01T00:00:00Z"}},
                }
            ],
        )
        prepare_company_bundle(**args)
        out = Path(args["output"])
        record = json.loads((out / "records.jsonl").read_text())
        # A state code in SEC's country slot means the United States.
        assert record["business_address"] == {
            "street": "1 Main Street",
            "street2": None,
            "city": "Cupertino",
            "region": "CA",
            "postal_code": "95014",
            "country": "US",
        }
        census = json.loads((out / "name-census.json").read_text())
        assert (
            record["name_census"]["census"] == record["_origin"]["name_census_sha256"]
        )
        assert record["name_census"]["ciks"] == ["0000320193"]
        assert record["name_census"]["leis"] == [
            ["HWUPKR0MPOU8FGXBT394", "2026-09-01T00:00:00Z"]
        ]
        assert census["sec"]["filers"] == 1
        key = json.loads((out / "manifest.json").read_text())["batches"][0]["input"][
            "publication"
        ]["publication_key"]
        assert key.endswith(f":name_census:{record['name_census']['census']}")
        assert ":sec_company_address:" in key

    def test_a_filer_without_a_business_address_carries_none(self, tmp_path):
        args = landing(tmp_path, [source_row(123)])
        prepare_company_bundle(**args)
        record = json.loads((Path(args["output"]) / "records.jsonl").read_text())
        assert record["business_address"] is None

    def test_a_census_of_another_capture_is_refused(self, tmp_path):
        args = landing(tmp_path, [source_row(123)])
        other = landing(tmp_path / "other", [source_row(123), source_row(456)])
        with pytest.raises(Conflict, match="did not count this Company capture"):
            prepare_company_bundle(**{**args, "name_census": other["name_census"]})

    def test_the_record_carries_its_matching_evidence_in_provenance(self):
        row = source_row(320193, entity_name="APPLE INC")
        row["last_synced_at"] = row["last_synced_at"].isoformat()
        row["business_address"] = {"postal_code": "95014", "country": "US"}
        row["name_census"] = {"census": "c" * 64, "key": "APPLE INC"}
        body = normalize(
            row,
            source_code=SOURCE_CODE,
            contract=CONTRACT,
            publication={
                "publication_key": "capture-1/company",
                "revision": 0,
                "effective_at": None,
                "artifact_sha256": "a" * 64,
                "member": "records.jsonl",
            },
        )
        assert body["provenance"]["matching"] == {
            "business_postal_code": "95014",
            "business_country": "US",
            "name_census": {"census": "c" * 64, "key": "APPLE INC"},
        }
        # Matching evidence grants no field a value.
        assert "business_postal_code" not in body["fields"]
        assert body["fields"]["address"] == {
            "op": "value",
            "value": {"postcode": "95014", "country": "US"},
        }


class TestEachRecordNamesItsBronzeObject:
    """Ticket 10: a record names the bronze object it was read from."""

    def records(self, args):
        prepare_company_bundle(**args)
        folder = Path(args["output"])
        return [
            json.loads(line)
            for line in (folder / "records.jsonl").read_text().splitlines()
        ]

    def test_a_record_names_its_raw_objects_storage_path_and_hash(self, tmp_path):
        args = landing(
            tmp_path,
            [source_row(123), source_row(456)],
            raw_objects=[raw_object_row(123)],
        )
        found = self.records({**args, "limit": 2})
        assert found[0]["_origin"]["bronze"] == {
            "object": "bronze/submissions/cik=123/CIK0000000123.json",
            "sha256": hashlib.sha256(b"123").hexdigest(),
            "locator": "$",
        }
        # Its raw object was not landed by this capture: it names none.
        assert "bronze" not in found[1]["_origin"]
        report = prepare_company_bundle(**{**args, "limit": 2})
        assert report["scope"]["bronze_named"] == 1
        assert "raw-objects.parquet" in report["files"]

    def test_the_record_itself_is_unchanged(self, tmp_path):
        with_bronze = self.records(
            landing(tmp_path, [source_row(123)], raw_objects=[raw_object_row(123)])
        )[0]
        without = copy.deepcopy(with_bronze)
        del without["_origin"]["bronze"]
        publication = {
            "publication_key": "p",
            "revision": 0,
            "effective_at": None,
            "artifact_sha256": "a" * 64,
            "member": "m",
        }
        read = [
            normalize(
                row, source_code=SOURCE_CODE, contract=CONTRACT, publication=publication
            )
            for row in (with_bronze, without)
        ]
        assert read[0] == read[1]

    def test_a_capture_without_raw_objects_names_none(self, tmp_path):
        report = prepare_company_bundle(**landing(tmp_path, [source_row(123)]))
        assert report["scope"]["bronze_named"] == 0
        assert "raw-objects.parquet" not in report["files"]

    def test_a_raw_object_without_a_digest_is_refused(self, tmp_path):
        args = landing(
            tmp_path, [source_row(123)], raw_objects=[raw_object_row(123, sha256="ABC")]
        )
        with pytest.raises(Conflict, match="lowercase digest"):
            prepare_company_bundle(**args)
