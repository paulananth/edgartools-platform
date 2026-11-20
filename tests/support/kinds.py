"""Write an engine catalog whose kinds are an invented list, as the RDM code set it pins."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from edgar_warehouse.mdm import catalog
from edgar_warehouse.rules import files


def write_catalog(root: Path, body: dict) -> None:
    """`body`'s kinds published under `root` as code set mdm-kinds, version `test`, and the catalog pinning it."""
    data = "".join(json.dumps({"code": kind, "definition": "Invented.", "properties": {"golden_records": False}})
                   + "\n" for kind in body["kinds"]).encode()
    folder = root / "reference" / "published" / "mdm-kinds" / "test"
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "canonical.jsonl").write_bytes(data)
    pinned = {**body, "kinds": {"code_set": "mdm-kinds", "version": "test", "sha256": hashlib.sha256(data).hexdigest()}}
    (root / catalog.RELATIVE).parent.mkdir(parents=True, exist_ok=True)
    (root / catalog.RELATIVE).write_text(files.dumps(pinned))
