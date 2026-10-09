"""Immutable preparation and staging boundaries without database effects."""
import hashlib
from pathlib import Path

import pytest

from edgar_warehouse.bookkeeping.clean.artifacts import Artifacts
from edgar_warehouse.workers import mdm_merge, mdm_prepare


def test_preparation_chunks_rows_and_verifies_every_records_file(tmp_path):
    store = Artifacts()
    source = hashlib.sha256(b"captured").hexdigest()
    reading = store.put(tmp_path.as_uri(), {"version": 1, "artifacts": [
        {"input": {"sha256": source}, "tables": {"company": [{"id": n} for n in range(1001)]}}
    ]})
    envelope = {"input": reading, "output": (tmp_path / "prepared" / "manifest.json").as_uri(),
                "checks": ["mdm.prepared"], "keys": {
                    "table": "company", "dataset": "fixture.company", "policy": "a" * 64,
                    "consumer": "fixture", "batch_id": "fixture", "as_of": "2026-01-01T00:00:00Z"}}
    candidate = mdm_prepare.execute(envelope, store)
    assert mdm_prepare.execute(envelope, store) == candidate
    manifest = store.json(candidate)
    assert [b["input"]["record_count"] for b in manifest["batches"]] == [1000, 1]
    assert [(b["expected_checkpoint"], b["checkpoint"]) for b in manifest["batches"]] == [(0, 1), (1, 2)]
    assert mdm_prepare.verify({**envelope, "candidate": candidate}, store) == ({"mdm.prepared": True}, [])
    (tmp_path / "prepared" / manifest["batches"][1]["input"]["path"]).write_bytes(b"corrupted\n")
    with pytest.raises(ValueError, match="records file.*differs"):
        mdm_prepare.verify({**envelope, "candidate": candidate}, store)


@pytest.mark.parametrize("name", ["../escape.jsonl", "/absolute.jsonl", "manifest.json"])
def test_staging_refuses_input_paths_that_escape_or_replace_the_manifest(tmp_path, name):
    store = Artifacts()
    ref = store.put(tmp_path.as_uri(), {"batches": [{"input": {"path": name, "sha256": "a" * 64}}]})
    staging = tmp_path / "staging"
    staging.mkdir()
    with pytest.raises(ValueError, match="file beside the manifest"):
        mdm_merge._stage({"input": ref}, store, staging)
    assert (staging / "manifest.json").read_bytes() == store.verified(ref)


def _prepare(tmp_path, rows, **keys):
    store = Artifacts()
    reading = store.put(tmp_path.as_uri(), {"version": 1, "artifacts": [
        {"input": {"sha256": hashlib.sha256(b"captured").hexdigest()}, "tables": {"rows": rows}}
    ]})
    envelope = {"input": reading, "output": (tmp_path / "prepared" / "manifest.json").as_uri(),
                "checks": ["mdm.prepared"], "keys": {
                    "table": "rows", "dataset": "fixture.rows", "policy": "a" * 64,
                    "consumer": "fixture", "batch_id": "fixture", "as_of": "2026-10-09T00:00:00Z",
                    **keys}}
    return store, envelope


def test_an_effective_column_dates_each_publication(tmp_path):
    rows = [{"id": n, "published": "2026-06-30T00:00:00+00:00"} for n in range(1001)]
    store, envelope = _prepare(tmp_path, rows, effective_column="published")
    candidate = mdm_prepare.execute(envelope, store)
    batches = store.json(candidate)["batches"]
    assert [b["input"]["publication"]["effective_at"] for b in batches] == ["2026-06-30T00:00:00+00:00"] * 2
    assert mdm_prepare.verify({**envelope, "candidate": candidate}, store) == ({"mdm.prepared": True}, [])
    # Without the key, a publication states no effective time, as before.
    (tmp_path / "without").mkdir()
    store, envelope = _prepare(tmp_path / "without", rows)
    assert "effective_at" not in store.json(mdm_prepare.execute(envelope, store))["batches"][0]["input"]["publication"]


@pytest.mark.parametrize("values, problem", [
    (["2026-06-30T00:00:00+00:00", "2026-05-31T00:00:00+00:00"], "one effective time"),
    (["2026-06-30T00:00:00+00:00", "2026-06-30T00:00:00Z"], "one effective time"),
    (["2026-10-10T00:00:00Z"], "after the manifest's as_of"),
    (["2026-06-30T00:00:00+00:00", None], "one effective time"),
    ([None], "an instant with a timezone"),
    (["2026-06-30"], "an instant with a timezone"),
    (["06/30/2026"], "an instant with a timezone"),
    ([20260630], "an instant with a timezone"),
])
def test_an_effective_column_refuses_mixed_or_unzoned_times(tmp_path, values, problem):
    store, envelope = _prepare(tmp_path, [{"id": n, "published": v} for n, v in enumerate(values)],
                               effective_column="published")
    with pytest.raises(ValueError, match=problem):
        mdm_prepare.execute(envelope, store)


def test_an_effective_column_takes_a_utc_suffix_and_skips_an_empty_file(tmp_path):
    store, envelope = _prepare(tmp_path, [{"id": 1, "published": "2025-12-31T23:59:59Z"}],
                               effective_column="published")
    batch = store.json(mdm_prepare.execute(envelope, store))["batches"][0]
    assert batch["input"]["publication"]["effective_at"] == "2025-12-31T23:59:59Z"
    (tmp_path / "empty").mkdir()
    store, envelope = _prepare(tmp_path / "empty", [], effective_column="published")
    with pytest.raises(ValueError, match="holds no rows"):
        mdm_prepare.execute(envelope, store)


def test_an_effective_column_must_be_named_text(tmp_path):
    store, envelope = _prepare(tmp_path, [{"id": 1}], effective_column="")
    with pytest.raises(ValueError, match="effective_column must be nonempty text"):
        mdm_prepare.execute(envelope, store)


def test_a_prepared_effective_time_dates_the_records_mdm_reads(tmp_path):
    from edgar_warehouse.mdm.clean.adapters import normalize

    rows = [{"id": "7", "name": "Acme", "published": "2026-06-30T00:00:00+00:00"}]
    store, envelope = _prepare(tmp_path, rows, effective_column="published")
    batch = store.json(mdm_prepare.execute(envelope, store))["batches"][0]
    contract = {"schema_version": "fixture-v1", "adapter": {
        "version": "fixture-v1", "kind": "company", "record_key": ["id"],
        "field_shape": "nullable_text", "fields": {"legal_name": "name"}}}
    record = normalize(rows[0], source_code="fixture.rows", contract=contract,
                       publication={**batch["input"]["publication"], "artifact_sha256": "a" * 64,
                                    "member": batch["input"]["path"]})
    assert record["effective_at"] == "2026-06-30T00:00:00+00:00"


def test_links_stated_in_two_dated_files_fold_into_one_link_first_and_last_stated():
    """The purpose: a link restated by each file starts when first stated and
    shows when it was last stated; neither file states a start."""
    from types import SimpleNamespace

    from edgar_warehouse.mdm.clean import relationships

    entities = {e: {"kind": "company", "status": "accepted", "profiles": []} for e in ("E1", "E2")}
    state = SimpleNamespace(bindings={"S": "E1", "T": "E2"}, canonical={"E1": "E1", "E2": "E2"})
    link = {"type": "LINKED", "source_subject": "S", "target_subject": "T", "scope": "fixture"}
    claims = {f"L{n}": {"assertion_id": f"a{n}", "relationships": [link],
                        "source_meta": {"effective_at": effective_at}}
              for n, effective_at in enumerate(["2026-03-31T00:00:00+00:00", "2025-06-30T00:00:00+00:00"])}
    types = {"LINKED": {"from": ["company"], "to": ["company"]}}
    edges, reviews = relationships.project(claims, state, entities, "2026-10-09T00:00:00+00:00", types=types)
    assert reviews == []
    [edge] = edges
    assert [(p["valid_from"], p["valid_from_basis"], p.get("valid_to")) for p in edge["periods"]] == [
        ("2025-06-30T00:00:00+00:00", "observed", None)]
    assert edge["last_seen"] == "2026-03-31T00:00:00+00:00"
    # Undated, as before this key: no link.
    undated = {k: {**c, "source_meta": {"effective_at": None}} for k, c in claims.items()}
    edges, reviews = relationships.project(undated, state, entities, "2026-10-09T00:00:00+00:00", types=types)
    assert edges == [] and {r["reason"] for r in reviews} == {"unknown_relationship_start"}
