"""Which of a source's files a run must process (ticket 22).

The Change Journal decides per file, never per field: a file is identical,
and skipped, when the journal already records that this source processed
this file key with this content hash under the same processing identity.
The processing identity is the digest of the source's rules version (its
reading, Dataset Contract and the part of the policy that acts on it) and every shared input the run reads,
so a change to any of them processes every file again (operator,
2026-10-13: "Rules + shared inputs"). A forced run processes every file and
says so (`--all`). Recording happens in the run's last step,
`journal.record`, once its merge is verified.
"""

from __future__ import annotations

from datetime import UTC

from edgar_warehouse.change_journal.store import FOUND_LIMIT
from edgar_warehouse.control_contract import digest

PRODUCER = "change-propagation"
EVENT_TYPE = "file.processed"


def identity(rules, policy: str, shared: list[dict] | None = None) -> str:
    """The processing identity: the rules a run reads files under (the
    source's readings and Dataset Contracts, as their documents), the digest of
    the part of the merge policy that acts on the source (`source_policy_digest`:
    its rules, their identifier contracts and the kind's field defaults, so a rule
    of another source does not process these files again), and every shared input
    by name and sha256 (a name count, a catalog)."""
    return digest({"rules": rules, "policy": policy,
                   "shared": sorted((s["name"], s["sha256"]) for s in shared or [])})


KEY_BYTES = 2048  # the journal's bound on an event key


def event_key(source: str, processing: str, key: str, sha256: str) -> str:
    """One file's key: its source, the processing identity, its content hash
    and its key; refused before any work when the journal could not hold it."""
    found = f"{EVENT_TYPE}:{source}:{processing}:{sha256}:{key}"
    if len(found) > KEY_BYTES:
        raise ValueError(f"A file key too long for the Change Journal: {key[:80]}...")
    return found


# `delivered` says where a run fact's value is read from; the identity holds the value itself.
HOW_HELD = frozenset({"grain", "lease_seconds", "heartbeat_seconds", "delivered"})


def source_rules(source: str) -> dict:
    """The source's rules version: every rules file in its folder, by name. A target is taken as the
    steps it gives (never its grain) and a rules file without what its pass reads (the steps hold that), so writing the same
    steps another way processes no file again."""
    from edgar_warehouse.rules import files as rules_files
    from edgar_warehouse.rules.shape import expand_source

    folder = rules_files.ROOT / "sources" / source
    found = {path.name: expand_source(rules_files.contract(path), folder) for path in sorted(folder.glob("*.yaml"))}
    # A target's grain, and what only a target held by the unit reads, say how much of its work Bookkeeping holds,
    # not what the work writes: changing one processes no file again.
    targets = ((found.get("source.yaml") or {}).get("bookkeeping") or {}).get("targets") or {}
    if any(HOW_HELD & set(target) for target in targets.values()):
        body = found["source.yaml"]
        found["source.yaml"] = {**body, "bookkeeping": {**body["bookkeeping"], "targets": {
            name: {key: value for key, value in target.items() if key not in HOW_HELD}
            for name, target in targets.items()}}}
    return found


def unprocessed(journal, source: str, processing: str, files: list[tuple[str, str]]) -> list[str]:
    """The keys of the files (key, sha256) the journal holds no record of, in their order."""
    keys = {event_key(source, processing, key, sha): key for key, sha in files}
    seen: set[str] = set()
    names = list(keys)
    for start in range(0, len(names), FOUND_LIMIT):
        seen |= journal.found(PRODUCER, names[start:start + FOUND_LIMIT])
    return [keys[name] for name in names if name not in seen]


_JOURNALS: dict = {}


def journal():
    """The Change Journal of this process: opened once for a database, since each new engine is a new database session
    (a persons bundle opened fifteen on a hosted store)."""
    import os

    from edgar_warehouse.change_journal.store import ChangeJournal, get_engine

    from edgar_warehouse.database_connections import configured, store_url

    url = str(store_url("change_journal")) if configured("change_journal") else ""
    if url not in _JOURNALS:
        _JOURNALS[url] = ChangeJournal(get_engine())
    return _JOURNALS[url]


def select(source: str, processing: str, files: list[tuple[str, str]], *, force: bool, ledger=None) -> list[str]:
    """The files a run names, in their order: every one when forced, else the unprocessed."""
    if force:
        return [key for key, _ in files]
    return unprocessed(ledger or journal(), source, processing, files)


def record_input(*, source: str, feed: str, processing: str, files: list[dict], forced: bool, as_of: str) -> dict:
    """What `journal.record` appends: one event per named file (its key,
    receipt URI and sha256), dated `as_of`, the run's own time in UTC."""
    from edgar_warehouse.mdm.evidence import instant

    occurred = instant(as_of).astimezone(UTC).isoformat()
    return {"version": 1, "source": source, "feed": feed, "identity": processing, "forced": forced,
            "occurred_at": occurred,
            "files": sorted(({"key": f["key"], "uri": f["uri"], "sha256": f["sha256"]} for f in files),
                            key=lambda f: f["key"])}
