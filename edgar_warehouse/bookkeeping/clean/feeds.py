"""Shared read-only source/feed resolution for Bookkeeping and Change Journal."""

from pathlib import Path

from edgar_warehouse.rules.files import load

from .config import digest


def _acquires(body: dict, feed: str) -> bool:
    declared = body.get("acquisition", {}).get("feeds", {})
    return feed in declared or any(feed in value["datasets"] for value in declared.values())


def resolve_feed(root: Path, source: str, feed: str) -> dict:
    if not source or not feed:
        raise ValueError("Both source and feed are required")
    documents = [
        (path.parent.name, load(path))
        for path in sorted(root.glob("sources/*/source.yaml"))
    ]
    matches = [(name, body) for name, body in documents if name == source]
    if not matches:
        matches = [
            (name, body)
            for name, body in documents
            if any(
                entry["contract"].get("provider", "").casefold() == source.casefold()
                for entry in body.get("mdm", {}).values()
            )
        ]
    if len(matches) > 1:
        # Several documents may read one provider's files (SEC submissions
        # feed Company and Person); the one that acquires the feed answers.
        matches = [(name, body) for name, body in matches if _acquires(body, feed)]
        if len(matches) != 1:
            raise ValueError(
                f"Source {source!r} names several Rules documents, and {len(matches)} of them "
                f"acquire feed {feed!r}; exactly one must"
            )
    if len(matches) != 1:
        raise ValueError(
            f"Source {source!r} must resolve to exactly one Rules document"
        )
    name, body = matches[0]
    if body.get("source") != name:
        raise ValueError("Rules source identity disagrees with its document name")
    requested_feed = feed
    declared = body.get("acquisition", {}).get("feeds", {})
    aliases = [name for name, value in declared.items() if feed in value["datasets"]]
    if feed not in declared and len(aliases) == 1:
        feed = aliases[0]
    declared_feed = declared.get(feed)
    bronze_family = body.get("bronze", {}).get("family")
    datasets = []
    for code, entry in sorted(body.get("mdm", {}).items()):
        contract = entry["contract"]
        member = contract.get("adapter", {}).get("native_member")
        labels = {code, member, bronze_family, contract.get("family")}
        labels.update(contract.get("publication_families", []))
        if (
            feed in labels
            or declared_feed is not None
            and code in declared_feed["datasets"]
        ):
            datasets.append(
                {
                    "code": code,
                    "member": member,
                    "family": contract.get("family"),
                    "publication_families": contract.get("publication_families", []),
                }
            )
    if declared_feed is None:
        raise ValueError(f"Feed {feed!r} is not declared by source {name!r}")
    return {
        "source": name,
        "requested_source": source,
        "feed": feed,
        "requested_feed": requested_feed,
        "rules_digest": digest(body),
        "datasets": datasets,
        "targets": sorted(body.get("bookkeeping", {}).get("targets", {})),
    }
