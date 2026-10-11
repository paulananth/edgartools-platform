"""Ticket 07: one JSON Lines record per ownership document (Forms 3, 4, 5).

The profiler reads each child of an XML root as a record, which splits one
filing into its parts (issuer, owner, tables). Wrapping each document in one
outer element makes the whole document one record, converted by the
profiler's own XML reader. The accession and the folder's CIK come from the
path. Read-only over the local copy; no requests.

    uv run --no-sync python to_jsonl.py <bronze root> <out.jsonl> [primary|artifact]
"""
from __future__ import annotations

import io
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[5] / "skills/data-profiling/scripts"))
from profiling.inputs import _xml_records  # noqa: E402


def documents(root: Path, which: str):
    if which == "primary":
        for path in sorted(root.glob("filings/sec/*/*/primary/*.xml")):
            body = path.read_bytes()
            if b"ownershipDocument" in body[:20000]:
                cik = re.search(r"cik=(\d+)", str(path)).group(1)
                accession = re.search(r"accession=([\d-]+)", str(path)).group(1)
                yield {"accession": accession, "folder_cik": cik, "file": path.name}, body
    else:
        # Whole submission files: an SGML header, then the document's XML
        # between <XML> and </XML>.
        for path in sorted((root / "filing_artifact").iterdir()):
            text = path.read_bytes()
            accession = re.search(rb"ACCESSION NUMBER:\s*([\d-]+)", text).group(1).decode()
            xml = re.search(rb"<XML>(.*?)</XML>", text, re.S).group(1).strip()
            yield {"accession": accession, "artifact_sha256": path.name}, xml


def main(root: Path, out: Path, which: str) -> None:
    n = 0
    with out.open("w") as sink:
        for meta, body in documents(root, which):
            body = re.sub(rb"^\s*<\?xml[^>]*\?>", b"", body.strip())
            record = next(_xml_records(io.BytesIO(b"<documents>" + body + b"</documents>")))
            sink.write(json.dumps({**meta, **record}) + "\n")
            n += 1
    print(json.dumps({"documents": n, "out": str(out)}))


if __name__ == "__main__":
    main(Path(sys.argv[1]), Path(sys.argv[2]), sys.argv[3] if len(sys.argv) > 3 else "primary")
