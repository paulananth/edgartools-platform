"""The rules files, frozen for a run.

The files under `rules/` are the rules. A run takes one document (a source, a pipeline or the merge
rules), checks it as `rules check` does and freezes it under the digest of its body: that export is
what Bookkeeping pins and every worker of the run reads. Nothing is saved, proved, approved or
activated first.

A source's Dataset Contracts and the merge rules are also registered in MDM, where the Merge Stage
reads them. `register` does that from the same files, and changes nothing when they are registered.
"""

from __future__ import annotations

from pathlib import Path

from edgar_warehouse.control_contract import Blocked, digest

from . import files

KINDS = ("source", "pipeline", "merge")


def of(kind: str, name: str, body: dict) -> dict:
    """A document's body, checked, with its digest. Its version is the digest's first twelve characters:
    a name for people, never a second identity."""
    if kind not in KINDS:
        raise Blocked("A document is a source, a pipeline or the merge rules")
    files.check_document(kind, body)
    content = digest(body)
    return {"kind": kind, "name": name, "version": content[:12], "digest": content, "body": body}


def export(kind: str, name: str, root: Path | None = None) -> dict:
    """One document of the rules folder, frozen."""
    found = {(k, n): path for k, n, path in files.documents(root)}
    if (kind, name) not in found:
        raise Blocked(f"The rules folder holds no {kind} named {name}")
    return of(kind, name, files.LAYOUT[kind][0](found[(kind, name)]))


def register(conn, sources: list[str] | None = None, root: Path | None = None) -> dict:
    """Register the merge rules and each named source's Dataset Contracts in MDM (every source's, when
    none is named), on the store owner's connection. Registering what is registered changes nothing."""
    from edgar_warehouse.mdm.store import current_reading, register_dataset, register_policy

    receipts = {"policy_digest": register_policy(conn, export("merge", "platform", root)["body"]), "datasets": {}}
    names = sources if sources is not None else [name for kind, name, _ in files.documents(root) if kind == "source"]
    for name in names:
        frozen = export("source", name, root)
        for code, entry in (frozen["body"].get("dataset_contracts") or {}).items():
            existing = (current_reading(conn, code) or (None, None))[1]
            # A dataset belongs to the source that first registered it.
            owner = (((existing or {}).get("registry_evidence") or {}).get("rules") or {}).get("name")
            if owner is not None and owner != name:
                raise Blocked(f"Dataset {code} belongs to source {owner}, not {name}")
            if existing is None or {k: v for k, v in existing.items() if k != "registry_evidence"} != entry["contract"]:
                register_dataset(conn, code, entry["contract"], rules_authority=frozen)
            version, reading = current_reading(conn, code)
            receipts["datasets"][code] = {"source": name, "mapping_version": version, "digest": digest(reading)}
    return receipts
