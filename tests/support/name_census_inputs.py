"""GLEIF inputs for a Name Census in tests: a Golden Copy archive and its configured reading."""

import hashlib
import json


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


def gleif_reading(folder, archive, wanted, count):
    """The Golden Copy through its configured complete reading, as the `source.read` worker writes it."""
    from edgar_warehouse.bookkeeping.clean.artifacts import Artifacts
    from edgar_warehouse.mdm.clean.name_frequency import GLEIF_READING
    from edgar_warehouse.rules import files
    from edgar_warehouse.workers import source_read

    folder.mkdir()
    store = Artifacts()
    source = store.put_bytes((folder / archive.name).as_uri(), archive.read_bytes())
    context = store.put(folder.as_uri(), {"version": 1, "input": source, "values": {"publication_count": count}})
    lookups = store.put(folder.as_uri(), {"version": 1, "input": source, "sets": {"wanted": sorted(wanted)}})
    contract = store.put(folder.as_uri(), files.load(GLEIF_READING))
    request = store.put(folder.as_uri(), {"version": 3, "contract": contract,
                                          "artifacts": [{"input": source, "context": context, "lookups": lookups}]})
    task = {"input": request, "output": (folder / "reading.json").as_uri(), "checks": ["source.output"]}
    candidate = source_read.execute(task, store)
    assert source_read.verify({**task, "candidate": candidate}, store) == ({"source.output": True}, [])
    return candidate
