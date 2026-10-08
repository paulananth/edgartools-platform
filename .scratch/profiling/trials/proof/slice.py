"""Profiling ticket 08: slice the local feeds to the cohort, once.

The recreation proof reads only these slices (operator, 2026-10-07: "Local
feeds only (Recommended)"). Every input is local and read only; nothing is
requested from any provider. Output, outside the repository:

    ~/.local/share/edgartools/clean-mdm/proving/p08/inputs/
      sec/        the cohort's SEC submissions documents, at their bronze keys,
                  the ticker catalog of the same capture, and receipts.jsonl
      gleif/      level1.jsonl, relationships.jsonl, reporting_exceptions.jsonl:
                  one native Golden Copy record per line, with its ordinal
      13f/        the cohort filers' 13F information tables on this machine
      SLICE.json  what was taken, why, sizes, sha256 of each file and times

The GLEIF set: every LEI of a cohort entity (its own, or one the Name Census
of ticket 27 names for its name), then every LEI a relationship record links
to one of those, then every successor a Level 1 record of the set names.

    uv run --no-sync --with ijson python .scratch/profiling/trials/proof/slice.py
"""

from __future__ import annotations

import hashlib
import json
import shutil
import time
import zipfile
from pathlib import Path

import ijson

HERE = Path(__file__).resolve().parent
COHORT = HERE.parent / "cohort" / "cohort.json"
LOCAL = Path.home() / ".local/share/edgartools"
CAPTURE = LOCAL / "clean-mdm/captures/sec.submissions.company/all-76230"
CENSUS = LOCAL / "clean-mdm/proving/cm27/census.json"
GLEIF = LOCAL / "clean-mdm/research/gleif-20260911-1600"
THIRTEENF = LOCAL / "heavy-parse-13f"
THIRTEENF_PIN = HERE.parents[3] / "docs/research/heavy-parse-s3-pin-13f-2026-09-25.json"
OUT = LOCAL / "clean-mdm/proving/p08/inputs"
PREFIX = "warehouse/bronze/"
TICKERS = "warehouse/bronze/reference/sec/company_tickers_exchange/2026/09/02/company_tickers_exchange.json"
ARCHIVES = {
    "level1": ("01-20260911-1600-gleif-goldencopy-lei2-golden-copy.json.zip",
               "1b6cd9cda3f94269fd406ee481842ea042b699e95eb5b8124b1496d4fda36a6a", "records.item"),
    "relationships": ("01-20260911-1600-gleif-goldencopy-rr-golden-copy.json.zip",
                      "089a2513d2b5d78fc6359c87ef4bc25a56ac7f58d6b3cb740b954e3ecd2bd0c3", "relations.item"),
    "reporting_exceptions": ("01-20260911-1600-gleif-goldencopy-repex-golden-copy.json.zip",
                             "f205fd8dfc8dc04587fcd2465b741562bf39af3835916314b96033982023e831", "exceptions.item"),
}


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        while chunk := f.read(1024**2):
            h.update(chunk)
    return h.hexdigest()


def lei_of(row: dict) -> str | None:
    return (row.get("LEI") or {}).get("$")


def ends(row: dict) -> list[str | None]:
    rel = (row.get("RelationshipRecord") or {}).get("Relationship") or {}
    return [((rel.get(side) or {}).get("NodeID") or {}).get("$") for side in ("StartNode", "EndNode")]


def successors(row: dict) -> set[str]:
    items = (row.get("Entity") or {}).get("SuccessorEntity") or []
    items = items if isinstance(items, list) else [items]
    return {(item.get("SuccessorLEI") or {}).get("$") for item in items if isinstance(item, dict)} - {None}


def scan(member: str, keep) -> tuple[list[tuple[int, dict]], float]:
    """One pass of a Golden Copy member: its sha256 checked, then streamed (ijson's C parser).

    The production reader (`inspect_archive`) also snapshots the archive and
    checks every record's framing, about ten times slower; a slice needs only
    the publication's own bytes, which the sha256 proves.
    """
    name, digest, item = ARCHIVES[member]
    started, rows = time.monotonic(), []
    if sha256(GLEIF / name) != digest:
        raise SystemExit(f"{name}: sha256 differs")
    with zipfile.ZipFile(GLEIF / name) as archive, archive.open(archive.namelist()[0]) as stream:
        for ordinal, row in enumerate(ijson.items(stream, item, use_float=True)):
            if keep(row):
                rows.append((ordinal, row))
    return rows, round(time.monotonic() - started, 1)


def write_jsonl(path: Path, rows: list[tuple[int, dict]]) -> None:
    with path.open("w") as f:
        for ordinal, row in rows:
            f.write(json.dumps({"ordinal": ordinal, "record": row}, ensure_ascii=False, default=str) + "\n")


def main() -> None:
    cohort = json.loads(COHORT.read_text())["entities"]
    if OUT.exists():
        raise SystemExit(f"{OUT} exists: the slice is made once; remove it to remake it")
    for part in ("sec", "gleif", "13f"):
        (OUT / part).mkdir(parents=True)
    report: dict = {"cohort": str(COHORT.relative_to(HERE.parents[3])), "entities": len(cohort), "times": {}}

    # SEC: each cohort document and the ticker catalog, checked against the capture's receipts.
    started = time.monotonic()
    receipts = {}
    for line in (CAPTURE / "receipts.jsonl").open():
        row = json.loads(line)
        if "key" in row:
            receipts[row["key"]] = row
    keys = [e["submissions_key"] for e in cohort if e["submissions_key"]] + [TICKERS]
    with (OUT / "sec" / "receipts.jsonl").open("w") as out:
        for key in keys:
            source, target = CAPTURE / "bronze" / key.removeprefix(PREFIX), OUT / "sec" / key
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
            if sha256(target) != receipts[key]["sha256"]:
                raise SystemExit(f"{key}: sha256 differs from the capture's receipt")
            out.write(json.dumps(receipts[key], sort_keys=True) + "\n")
    report["sec"] = {"documents": len(keys) - 1, "ticker_catalog": TICKERS,
                     "bytes": sum(receipts[k]["bytes"] for k in keys)}
    report["times"]["sec_seconds"] = round(time.monotonic() - started, 1)

    # GLEIF: the cohort's LEIs, then linked LEIs, then successors.
    ciks = {e["cik"] for e in cohort}
    own = {e["lei"] for e in cohort if e["lei"]}
    census = json.loads(CENSUS.read_text())["entries"]
    named = {lei for entry in census.values() if ciks & set(entry["ciks"]) for lei, *_ in entry["leis"]}
    seed = own | named
    links, report["times"]["relationships_seconds"] = scan("relationships", lambda r: bool(seed & set(ends(r))))
    linked = {e for _, r in links for e in ends(r) if e} - seed
    wanted = seed | linked
    level1, report["times"]["level1_seconds"] = scan("level1", lambda r: lei_of(r) in wanted)
    later = {s for _, r in level1 for s in successors(r)} - wanted
    if later:
        more, report["times"]["level1_successors_seconds"] = scan("level1", lambda r: lei_of(r) in later)
        level1 = sorted(level1 + more, key=lambda pair: pair[0])
    leis = wanted | later
    exceptions, report["times"]["reporting_exceptions_seconds"] = scan("reporting_exceptions", lambda r: lei_of(r) in leis)
    for member, rows in (("level1", level1), ("relationships", links), ("reporting_exceptions", exceptions)):
        write_jsonl(OUT / "gleif" / f"{member}.jsonl", rows)
    report["gleif"] = {
        "publication": "GLEIF Golden Copy 2026-09-11 16:00",
        "leis": {"cohort_own": len(own), "named_by_census": len(named - own), "linked": len(linked),
                 "successors": len(later), "all": len(leis)},
        "records": {"level1": len(level1), "relationships": len(links), "reporting_exceptions": len(exceptions)},
        "archives": {member: {"file": name, "sha256": digest} for member, (name, digest, _) in ARCHIVES.items()},
    }

    # 13F: the information tables on this machine filed by a cohort filer (named by etag in the cache).
    pin = json.loads(THIRTEENF_PIN.read_text())["sample_1000"]
    cik_numbers = {int(c) for c in ciks}
    tables = [t for t in pin if int(t["key"].split("/")[4].split("=", 1)[1]) in cik_numbers]
    for table in tables:
        target = OUT / "13f" / table["key"]
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(THIRTEENF / table["etag"], target)
        if target.stat().st_size != table["size"]:
            raise SystemExit(f"{table['key']}: size differs from the pin")
    report["13f"] = {"tables": len(tables), "bytes": sum(t["size"] for t in tables),
                     "filers": len({t["key"].split("/")[4] for t in tables})}

    report["files"] = {str(p.relative_to(OUT)): sha256(p) for p in sorted(OUT.rglob("*")) if p.is_file()}
    (OUT / "SLICE.json").write_text(json.dumps(report, indent=1, sort_keys=True) + "\n")
    print(json.dumps({k: v for k, v in report.items() if k != "files"}, indent=1))


if __name__ == "__main__":
    main()
