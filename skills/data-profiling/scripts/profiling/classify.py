"""The five classes, decided by measurable tests (research note section 1.2).

Each class is a list of named tests over one part's facts. Confidence is the
share of its tests that pass; every test is reported with its value. A tie, or
no class passing most of its tests, is "unknown": never a guess.
"""

from __future__ import annotations

from typing import Callable

REFERENCE_ROWS = 10_000
METADATA_WORDS = {"file", "files", "hash", "sha", "sha256", "checksum", "md5", "path", "url", "uri", "size",
                  "bytes", "count", "run", "manifest", "page", "offset", "batch", "etag", "receipt"}

# class: [(test name, test over the facts, the measured value shown)]
Test = tuple[str, Callable[[dict], bool], Callable[[dict], object]]
TESTS: dict[str, list[Test]] = {
    "master": [
        ("has a unique key", lambda f: f["key_found"], lambda f: f["key"]),
        ("other parts point at it", lambda f: f["in_degree"] >= 1, lambda f: f["in_degree"]),
        ("points at few parts", lambda f: f["out_degree"] <= 2, lambda f: f["out_degree"]),
        ("has name-like text", lambda f: f["name_like"] >= 1, lambda f: f["name_like"]),
        ("smaller than the parts pointing at it", lambda f: f["rows"] <= f["rows_pointing"], lambda f: f["rows"]),
        ("has attributes besides codes and dates", lambda f: f["attributes"] >= 1, lambda f: f["attributes"]),
    ],
    "reference": [
        ("has a unique key", lambda f: f["key_found"], lambda f: f["key"]),
        ("other parts point at it", lambda f: f["in_degree"] >= 1, lambda f: f["in_degree"]),
        (f"at most {REFERENCE_ROWS} rows", lambda f: f["rows"] <= REFERENCE_ROWS, lambda f: f["rows"]),
        ("points at no other part", lambda f: f["out_degree"] == 0, lambda f: f["out_degree"]),
        ("no name-like text besides labels", lambda f: f["name_like"] == 0, lambda f: f["name_like"]),
        ("codes with label columns", lambda f: f["labels"] >= 1, lambda f: f["labels"]),
        ("only codes, labels and dates", lambda f: f["attributes"] <= 1, lambda f: f["attributes"]),
    ],
    "relationship": [
        ("key made of links to other parts", lambda f: f["key_links"] >= 2 and f["key_other"] <= 2,
         lambda f: {"links": f["key_links"], "other": f["key_other"]}),
        ("points at two or more parts", lambda f: f["out_degree"] >= 2 or f["self_ends"], lambda f: f["out_degree"]),
        ("nothing points at it", lambda f: f["in_degree"] == 0, lambda f: f["in_degree"]),
        ("few other columns", lambda f: f["other_columns"] <= 4, lambda f: f["other_columns"]),
    ],
    "transaction": [
        ("has a unique key", lambda f: f["key_found"], lambda f: f["key"]),
        ("points at other parts", lambda f: f["out_degree"] >= 1, lambda f: f["out_degree"]),
        ("few parts point at it", lambda f: f["in_degree"] <= 1, lambda f: f["in_degree"]),
        ("has an event time or measures", lambda f: f["event_time"] or f["measures"] >= 1,
         lambda f: {"event_time": f["event_time"], "measures": f["measures"]}),
        ("no name-like text", lambda f: f["name_like"] == 0, lambda f: f["name_like"]),
        ("at least as large as the parts it points at", lambda f: f["rows"] >= f["rows_pointed"], lambda f: f["rows"]),
    ],
    "metadata": [
        ("columns describe data (files, hashes, counts)", lambda f: f["metadata_share"] >= 0.5,
         lambda f: f["metadata_share"]),
        ("nothing points at it", lambda f: f["in_degree"] == 0, lambda f: f["in_degree"]),
        ("points at no other part", lambda f: f["out_degree"] == 0, lambda f: f["out_degree"]),
    ],
}


def classify(facts: dict) -> dict:
    """The class with the highest share of passing tests, all tests reported."""
    scored = {}
    for name, tests in TESTS.items():
        results = [{"class": name, "test": label, "value": value(facts), "passed": bool(check(facts))}
                   for label, check, value in tests]
        scored[name] = (sum(r["passed"] for r in results) / len(results), results)
    best = max(scored.values(), key=lambda s: s[0])[0]
    leaders = [name for name, (share, _) in scored.items() if share == best]
    chosen = leaders[0] if len(leaders) == 1 and best > 0.5 else "unknown"
    tests = scored[chosen][1] if chosen != "unknown" else [t for name in leaders for t in scored[name][1]]
    return {"class": chosen, "confidence": round(best, 3) if chosen != "unknown" else 0.0, "tests": tests,
            "runner_up": sorted(((round(s, 3), n) for n, (s, _) in scored.items() if n != chosen), reverse=True)[:1]}


STORE = {
    "master": ("mdm", "entities with identity and a lifecycle: MDM masters them"),
    "reference": ("rdm", "a small set of codes that gives other values their meaning: an RDM code set, published to silver"),
    "relationship": ("mdm_relationships", "links between masters: MDM relationships, traversed with recursive SQL"),
    "transaction": ("silver", "append-heavy events and measures read by wide scans: silver"),
    "metadata": ("bookkeeping", "describes deliveries, not the business: Bookkeeping or the catalog"),
    "unknown": ("bronze_only", "not classified with evidence: keep it raw until the operator decides"),
}


def store(cls: str) -> dict:
    where, why = STORE[cls]
    return {"store": where, "why": why, "advisory": True}
