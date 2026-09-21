"""Ticket 10 resolution: re-parse every proxy filing in the S3 bronze bucket locally.

Resolution criterion (ticket 10, reworded 2026-09-21): parse every DEF 14A
primary document in bronze with the fixed parser -- bronze reads only, zero SEC
requests, no Snowflake -- collapse the rows exactly as the dbt silver model does
since #680, and run research 01's quality check on the collapsed set, with a
hand-read attribution sample alongside.

Scope is the four forms the pipeline routes to this parser
(`edgar_warehouse.parsers.PROXY_FORMS`: DEF 14A, DEF 14A/A, DEFA14A, PRE 14A).
A filing's form comes from its company's bronze `submissions.json` (recent
block, then pagination files), and, for filings newer than that company's last
snapshot, from SEC's daily `form.idx` files captured in bronze
(`daily_index/sec/YYYY/MM/DD/form.YYYYMMDD.idx`) -- never from the file name.

Stages (each writes to --work; re-runnable, downloads cached):

  select  --filings-listing F --submissions-listing S [--daily-index-dir D]
          bronze primary documents -> (cik, accession, form); writes selected.jsonl
  parse   production `parse_proxy_fundamentals` over every selected document;
          writes rows.jsonl (one line per filing: rows + raw-entry count)
  score   dbt collapse (latest per cik, accession, fiscal_year, exec_name),
          research 01's check, research 10's check, hand-read sample;
          writes the JSON result to --out

Network guard: every DNS lookup is logged; any host under sec.gov raises.
S3 reads go to the bronze bucket only.

  uv run --extra s3 python 10-reparse-bronze.py select --work W \
      --filings-listing W/filings_listing.txt --submissions-listing W/submissions_listing.txt
  uv run --extra s3 python 10-reparse-bronze.py parse --work W
  uv run --extra s3 python 10-reparse-bronze.py score --work W --out 10-reparse-results.json
"""
from __future__ import annotations

import argparse
import concurrent.futures as cf
import importlib.util
import json
import random
import re
import socket
import sys
from collections import Counter, defaultdict
from pathlib import Path

BUCKET = "edgartools-prod-bronze-690839588395"
PREFIX = "warehouse/bronze/"
PROXY_FORMS = {"DEF 14A", "DEF 14A/A", "DEFA14A", "PRE 14A"}
HERE = Path(__file__).resolve().parent
SEED = 20260921

# ------------------------------------------------------------------ network guard
_HOSTS: Counter = Counter()
_real_getaddrinfo = socket.getaddrinfo


def _guarded_getaddrinfo(host, *a, **k):
    h = str(host or "")
    _HOSTS[h] += 1
    if h == "sec.gov" or h.endswith(".sec.gov"):
        raise RuntimeError(f"SEC request refused by ticket 10 guard: {h}")
    return _real_getaddrinfo(host, *a, **k)


socket.getaddrinfo = _guarded_getaddrinfo


def _s3():
    import s3fs

    return s3fs.S3FileSystem(anon=False)


_PRIMARY = re.compile(r"filings/sec/cik=(\d+)/accession=([0-9-]+)/primary/([^/]+)$")
_SUB_MAIN = re.compile(r"submissions/sec/cik=(\d+)/main/(\d{4}/\d{2}/\d{2})/[^/]+\.json$")
_IDX_LINE = re.compile(r"^(\S.*?)\s{2,}.*\s(\d{4,10})\s+\d{8}\s+edgar/data/\d+/([0-9-]+)\.txt\s*$")
_SUB_PAGE = re.compile(r"submissions/sec/cik=(\d+)/pagination/.*?([^/]+\.json)$")


def _keys(listing: Path) -> list[str]:
    out = []
    for line in listing.read_text().splitlines():
        parts = line.split(None, 3)
        if len(parts) == 4:
            out.append(parts[3])
    return out


# ------------------------------------------------------------------ select
def stage_select(args) -> None:
    work = Path(args.work)
    primaries: dict[tuple[int, str], list[str]] = defaultdict(list)
    upload_month: dict[tuple[int, str], str] = {}
    for line in Path(args.filings_listing).read_text().splitlines():
        parts = line.split(None, 3)
        if len(parts) != 4:
            continue
        m = _PRIMARY.search(parts[3])
        if m and m.group(3).lower().endswith((".htm", ".html")):
            primaries[(int(m.group(1)), m.group(2))].append(parts[3])
            upload_month[(int(m.group(1)), m.group(2))] = parts[0][:7]
    ciks = sorted({c for c, _ in primaries})

    main_by_cik: dict[int, tuple[str, str]] = {}
    pages_by_cik: dict[int, list[str]] = defaultdict(list)
    for key in _keys(Path(args.submissions_listing)):
        m = _SUB_MAIN.search(key)
        if m:
            cik, date = int(m.group(1)), m.group(2)
            if cik not in main_by_cik or date > main_by_cik[cik][0]:
                main_by_cik[cik] = (date, key)
            continue
        m = _SUB_PAGE.search(key)
        if m:
            pages_by_cik[int(m.group(1))].append(key)

    fs = _s3()
    subdir = work / "submissions"
    subdir.mkdir(parents=True, exist_ok=True)

    def fetch_json(key: str) -> dict:
        local = subdir / key.replace("/", "__")
        if not local.exists():
            local.write_bytes(fs.cat_file(f"{BUCKET}/{key}"))
        return json.loads(local.read_bytes())

    def forms_for(cik: int, wanted: set[str]) -> dict[str, str]:
        found: dict[str, str] = {}
        if cik not in main_by_cik:
            return found
        doc = fetch_json(main_by_cik[cik][1])
        recent = (doc.get("filings") or {}).get("recent") or {}
        for acc, form in zip(recent.get("accessionNumber") or [], recent.get("form") or []):
            if acc in wanted:
                found[acc] = form
        if wanted - set(found):
            for key in sorted(pages_by_cik.get(cik, [])):
                page = fetch_json(key)
                for acc, form in zip(page.get("accessionNumber") or [], page.get("form") or []):
                    if acc in wanted:
                        found[acc] = form
                if not (wanted - set(found)):
                    break
        return found

    wanted_by_cik: dict[int, set[str]] = defaultdict(set)
    for cik, acc in primaries:
        wanted_by_cik[cik].add(acc)

    form_of: dict[tuple[int, str], str] = {}
    with cf.ThreadPoolExecutor(16) as pool:
        futs = {pool.submit(forms_for, c, wanted_by_cik[c]): c for c in ciks}
        for i, fut in enumerate(cf.as_completed(futs), 1):
            c = futs[fut]
            for acc, form in fut.result().items():
                form_of[(c, acc)] = form
            if i % 1000 == 0:
                print(f"  forms resolved for {i}/{len(ciks)} CIKs", file=sys.stderr)

    source_of = {k: "submissions" for k in form_of}
    idx_forms: dict[str, str] = {}
    if args.daily_index_dir:
        for idx in sorted(Path(args.daily_index_dir).rglob("form.*.idx")):
            for line in idx.read_text(errors="replace").splitlines():
                m = _IDX_LINE.match(line)
                if m:
                    idx_forms[m.group(3)] = m.group(1).strip()
        for k in primaries:
            if k not in form_of and k[1] in idx_forms:
                form_of[k] = idx_forms[k[1]]
                source_of[k] = "daily_index"

    forms = Counter(form_of.get(k, "<unknown>") for k in primaries)
    selected = []
    for (cik, acc), keys in sorted(primaries.items()):
        form = form_of.get((cik, acc))
        if form in PROXY_FORMS:
            # One primary document per accession; if bronze holds several, take the largest-named
            # deterministic first (sorted) and record the count.
            selected.append({"cik": cik, "accession": acc, "form": form,
                             "key": sorted(keys)[0], "primary_docs": len(keys)})
    with open(work / "selected.jsonl", "w") as f:
        for row in selected:
            f.write(json.dumps(row) + "\n")
    summary = {
        "bronze_primary_html_accessions": len(primaries),
        "ciks": len(ciks),
        "ciks_without_a_submissions_snapshot": sum(1 for c in ciks if c not in main_by_cik),
        "accessions_with_unknown_form": forms["<unknown>"],
        "form_source": dict(Counter(source_of.values())),
        "daily_index_files": len(list(Path(args.daily_index_dir).rglob("form.*.idx"))) if args.daily_index_dir else 0,
        "unknown_form_upload_months": dict(Counter(
            upload_month.get(k, "") for k in primaries if k not in form_of)),
        "proxy_forms_selected": dict(Counter(r["form"] for r in selected)),
        "selected": len(selected),
        "accessions_with_more_than_one_primary_html": sum(1 for r in selected if r["primary_docs"] > 1),
        "top_forms": forms.most_common(15),
    }
    (work / "select-summary.json").write_text(json.dumps(summary, indent=1))
    print(json.dumps(summary, indent=1))


# ------------------------------------------------------------------ parse
_FS = None


def _parse_one(job: tuple[dict, str]) -> dict:
    """One filing, in a worker process: download (cached), extract, repair, parse."""
    global _FS
    from lxml import html as lxml_html
    from edgar.proxy.html_extractor import extract_summary_compensation

    from edgar_warehouse.parsers.proxy_fundamentals import (
        PARSER_VERSION,
        _repair_entry_names,
        parse_proxy_fundamentals,
    )

    row, docs = job
    local = Path(docs) / f"{row['cik']}_{row['accession']}.htm"
    if not local.exists():
        if _FS is None:
            _FS = _s3()
        local.write_bytes(_FS.cat_file(f"{BUCKET}/{row['key']}"))
    raw = local.read_bytes()
    content = raw.decode("utf-8", errors="replace")
    out = {**row, "bytes": len(raw), "parser_version": PARSER_VERSION}
    try:
        entries = extract_summary_compensation(lxml_html.fromstring(raw)) or []
        out["raw_entries"] = len(entries)
        out["raw_names"] = [str(e.name or "") for e in entries]
        out["repaired_entries"] = len(_repair_entry_names(list(entries)))
    except Exception as exc:  # noqa: BLE001
        out["raw_entries"] = None
        out["raw_error"] = repr(exc)[:200]
    try:
        parsed = parse_proxy_fundamentals(row["accession"], content, row["form"], row["cik"])
        out["rows"] = parsed.get("sec_executive_record", [])
    except Exception as exc:  # noqa: BLE001
        out["rows"] = []
        out["parse_error"] = repr(exc)[:200]
    out["hosts"] = dict(_HOSTS)
    return out


def stage_parse(args) -> None:
    work = Path(args.work)
    docs = work / "docs"
    docs.mkdir(exist_ok=True)
    selected = [json.loads(line) for line in open(work / "selected.jsonl")]
    rows_path = work / "rows.jsonl"
    done = {json.loads(line)["accession"] for line in open(rows_path)} if rows_path.exists() else set()
    todo = [r for r in selected if r["accession"] not in done]
    print(f"parse: {len(selected)} selected, {len(done)} already parsed, {len(todo)} to go", file=sys.stderr)
    hosts: Counter = Counter()
    with open(rows_path, "a") as f, cf.ProcessPoolExecutor(args.workers) as pool:
        for i, res in enumerate(pool.map(_parse_one, [(r, str(docs)) for r in todo], chunksize=4), 1):
            hosts.update(res.pop("hosts", {}))
            f.write(json.dumps(res, default=str) + "\n")
            if i % 250 == 0:
                f.flush()
                print(f"  parsed {i}/{len(todo)}", file=sys.stderr)
    prior = json.loads((work / "hosts.json").read_text()) if (work / "hosts.json").exists() else {}
    hosts.update(prior)
    (work / "hosts.json").write_text(json.dumps(dict(hosts), indent=1))


# ------------------------------------------------------------------ score
def _r17():
    spec = importlib.util.spec_from_file_location("c17", HERE / "17-common.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _r10_plausible():
    # research 10's check, verbatim (10-measure-repair.py) -- for continuity with the 149-doc sample.
    vocab = ["chief", "officer", "president", "chairman", "chairwoman", "chair ", "vice",
             "executive", "general counsel", "treasurer", "secretary", "controller",
             "principal", "director", "founder", "former", "interim", "senior", "head of",
             "board", "group", "division", "finance and", "operations"]

    def plausible(name: str) -> bool:
        if not name:
            return False
        low = " " + re.sub(r"\s+", " ", name.lower().replace(".", "").replace(",", "")).strip() + " "
        if any(v in low for v in vocab):
            return False
        return len([t for t in low.split() if t]) >= 2

    return plausible


_FOOTNOTE = re.compile(r"\(\s*[\d⁰¹²³⁴⁵⁶⁷⁸⁹*]+\s*\)|[⁰¹²³⁴⁵⁶⁷⁸⁹]|\(\s*\d")
_TRAILING_FRAGMENT = re.compile(r"\bCo-\s*$|-\s*$", re.IGNORECASE)


def stage_score(args) -> None:
    import os

    os.environ["R17_ALLOW_NET"] = "1"  # 17-common blocks sockets at import; scoring is offline anyway
    c17 = _r17()
    r10_plausible = _r10_plausible()
    work = Path(args.work)
    filings = [json.loads(line) for line in open(work / "rows.jsonl")]

    landing = []  # landing order = parse_sequence order
    for fl in filings:
        for row in fl.get("rows", []):
            landing.append(row)
    # dbt collapse (sec_executive_record.sql, #680): latest per (cik, accession, fiscal_year, exec_name)
    collapsed: dict[tuple, dict] = {}
    for seq, row in enumerate(landing):
        k = (row.get("cik"), row.get("accession_number"), row.get("fiscal_year"), row.get("exec_name"))
        collapsed[k] = row
    rows = list(collapsed.values())

    def r01_plausible(name: str) -> bool:  # research 01: no role vocabulary, >= 2 tokens
        return bool(name) and not c17.looks_like_role_text(name) and len(c17.norm_name(name).split()) >= 2

    names = [str(r.get("exec_name") or "") for r in rows]
    r01 = sum(1 for n in names if r01_plausible(n))
    r10 = sum(1 for n in names if r10_plausible(n))
    raw_before = [n for fl in filings for n in (fl.get("raw_names") or [])]
    bad = Counter(n for n in names if not r01_plausible(n))

    with_sct = [fl for fl in filings if fl.get("rows")]
    rng = random.Random(SEED)
    sample = rng.sample(rows, min(args.sample, len(rows)))
    by_acc = {fl["accession"]: fl for fl in filings}
    sample_out = [{
        "cik": r.get("cik"), "accession": r.get("accession_number"),
        "form": by_acc.get(r.get("accession_number"), {}).get("form"),
        "fiscal_year": r.get("fiscal_year"), "exec_name": r.get("exec_name"),
        "exec_role": r.get("exec_role"), "total_comp": r.get("total_comp"),
        "raw_names_in_filing": by_acc.get(r.get("accession_number"), {}).get("raw_names", [])[:12],
    } for r in sample]
    (work / "hand-read-sample.json").write_text(json.dumps(sample_out, indent=1, default=str))

    out = {
        "select": json.loads((work / "select-summary.json").read_text()),
        "filings_parsed": len(filings),
        "filings_with_a_summary_compensation_table": len(with_sct),
        "parse_errors": sum(1 for fl in filings if fl.get("parse_error")),
        "extract_errors": sum(1 for fl in filings if fl.get("raw_error")),
        "landing_rows": len(landing),
        "collapsed_rows": len(rows),
        "collapse_removed": len(landing) - len(rows),
        "raw_entries": sum(fl.get("raw_entries") or 0 for fl in filings),
        "rows_dropped_as_unattributable_by_repair":
            sum((fl.get("raw_entries") or 0) - (fl.get("repaired_entries") or 0) for fl in filings),
        "research_01_check": {"plausible": r01, "n": len(rows), "rate": round(r01 / len(rows), 5) if rows else None},
        "research_10_check": {"plausible": r10, "n": len(rows), "rate": round(r10 / len(rows), 5) if rows else None},
        "before_repair_research_10_check": {
            "plausible": sum(1 for n in raw_before if r10_plausible(n)), "n": len(raw_before),
            "rate": round(sum(1 for n in raw_before if r10_plausible(n)) / len(raw_before), 5) if raw_before else None},
        # Residues research 01's check tolerates (found in the hand-read sample):
        "residual_footnote_marker_in_name": {
            "rows": len(fn := [n for n in names if _FOOTNOTE.search(n)]),
            "rate": round(len(fn) / len(rows), 5) if rows else None,
            "top": Counter(fn).most_common(15)},
        "residual_trailing_hyphen_fragment": {
            "rows": len(fr := [n for n in names if _TRAILING_FRAGMENT.search(n)]),
            "rate": round(len(fr) / len(rows), 5) if rows else None,
            "top": Counter(fr).most_common(15)},
        "remaining_implausible_distinct": len(bad),
        "remaining_implausible_top": bad.most_common(60),
        "rows_by_form": dict(Counter(by_acc.get(r.get("accession_number"), {}).get("form") for r in rows)),
        "hosts_contacted": json.loads((work / "hosts.json").read_text()) if (work / "hosts.json").exists() else {},
        "sec_requests": 0,
        "hand_read_sample_size": len(sample_out),
        "seed": SEED,
    }
    Path(args.out).write_text(json.dumps(out, indent=1, default=str))
    print(json.dumps({k: v for k, v in out.items() if k != "remaining_implausible_top"}, indent=1, default=str))


def main() -> None:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="stage", required=True)
    s = sub.add_parser("select")
    s.add_argument("--work", required=True)
    s.add_argument("--filings-listing", required=True)
    s.add_argument("--submissions-listing", required=True)
    s.add_argument("--daily-index-dir")
    p = sub.add_parser("parse")
    p.add_argument("--work", required=True)
    p.add_argument("--workers", type=int, default=8)
    c = sub.add_parser("score")
    c.add_argument("--work", required=True)
    c.add_argument("--out", required=True)
    c.add_argument("--sample", type=int, default=60)
    args = ap.parse_args()
    {"select": stage_select, "parse": stage_parse, "score": stage_score}[args.stage](args)


if __name__ == "__main__":
    main()
