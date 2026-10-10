"""findings.yaml for agents and REPORT.md for the operator, from one findings document."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import yaml

from . import hierarchy


FINGERPRINTS = "fingerprints.json"


def write(findings: dict, out: Path) -> tuple[Path, Path]:
    out.mkdir(parents=True, exist_ok=True)
    data, report = out / "findings.yaml", out / "REPORT.md"
    findings = dict(findings)
    marked = findings.pop("marked_rows", [])
    with (out / "invalid_rows.jsonl").open("w", encoding="utf-8") as handle:
        for row in marked:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
    # Each part's key sample (thousands of hashes) goes beside the findings, never inside the file the
    # operator approves; the findings keep how many keys it holds and the file's sha256.
    samples = {p["part"]: p["fingerprint"]["keys"] for p in findings["parts"] if (p.get("fingerprint") or {}).get("keys")}
    text = json.dumps(samples, sort_keys=True)
    (out / FINGERPRINTS).write_text(text, encoding="utf-8")
    digest = hashlib.sha256(text.encode()).hexdigest()
    findings["parts"] = [{**p, "fingerprint": {**{k: v for k, v in p["fingerprint"].items() if k != "keys"},
                                               "sampled": len(samples.get(p["part"], {})),
                                               "file": FINGERPRINTS, "file_sha256": digest}}
                         if p.get("fingerprint") else p for p in findings["parts"]]
    data.write_text(yaml.safe_dump(findings, sort_keys=False, allow_unicode=True, width=120), encoding="utf-8")
    report.write_text(markdown(findings), encoding="utf-8")
    return data, report


def read_fingerprints(findings: dict, folder: Path) -> None:
    """Put each part's key sample back from the fingerprints.json beside approved findings, refusing one
    whose sha256 is not the one the findings recorded. Findings without one compare without samples."""
    path = folder / FINGERPRINTS
    if not path.exists():
        return
    text = path.read_text(encoding="utf-8")
    samples, digest = json.loads(text), hashlib.sha256(text.encode()).hexdigest()
    for p in findings["parts"]:
        f = p.get("fingerprint")
        if f and f.get("file") == FINGERPRINTS:
            if f["file_sha256"] != digest:
                raise SystemExit(f"{path} differs from the one the approved findings recorded")
            f["keys"] = samples.get(p["part"], {})


def markdown(f: dict) -> str:
    d = f["dataset"]
    lines = [f"# Profiling report: {d['name']}", "",
             f"Profiled {d['profiled_at']} by {d['profiled_by']}. Scan: **{d['scan']['mode']}**"
             + (f" ({d['scan']['reason']}, seed {d['scan']['seed']})" if d["scan"]["mode"] == "sampled" else "")
             + f"; {d['scan']['elapsed_seconds']} s. Approval: **{f['approval']['status']}**.", "",
             "## Parts", "", "| Part | Rows | Class | Confidence | Record key | Store (advice) |", "|---|---|---|---|---|---|"]
    for p in f["parts"]:
        key = p["record_key"]
        shown = ", ".join(key["columns"]) + ("" if key["found"] else f" (designed: {key['design']})")
        lines.append(f"| {p['part']} | {p['rows']} | {p['class']} | {p['confidence']} | {shown} | "
                     f"{p['store_suggestion']['store']} |")
    lines += ["", "## Why each class", ""]
    for p in f["parts"]:
        passed = [t["test"] for t in p["tests"] if t["passed"]]
        failed = [t["test"] for t in p["tests"] if not t["passed"]]
        found_in = f" (an entity found inside {p['derived_from']})" if p.get("derived_from") else ""
        lines.append(f"- **{p['part']}**{found_in} is {p['class']}: " + "; ".join(passed)
                     + (f". Failed: {'; '.join(failed)}." if failed else "."))
    lines += ["", "## Relationships", "", "| From | To | Inclusion | Cardinality | Onboard | Why |", "|---|---|---|---|---|---|"]
    for r in f["relationships"]:
        lines.append(f"| {r['from']['part']}.{', '.join(r['from']['columns'])} | {r['to']['part']}."
                     f"{', '.join(r['to']['columns'])} | {r['inclusion']} | {r['cardinality']} | {r['onboard']} | {r['why']} |")
    lines += ["", "## Hierarchies", ""]
    for h in f["hierarchies"] or [{"hierarchy": "none found"}]:
        if "type" not in h:
            lines.append("None found.")
            continue
        lines.append(f"- **{h['hierarchy']}** ({h['type']}, {h['evidence_kind']}): {h['rule']}; holds {h['holds']}, "
                     f"depth {h['depth']}, {h['shape']}, orphans {h['orphans']}, cycles {h['cycles']}, "
                     f"invalid rows {h['invalid_rows']}.")
    rejected = f.get("dependencies_not_hierarchies") or []
    if rejected:
        lines += ["", f"Dependencies that are not hierarchies: a yes/no flag (never a level), or a coincidence "
                      f"(lift over guessing the parent's commonest value below {hierarchy.LIFT}, or under "
                      f"{hierarchy.SUPPORT:.0%} of the rows with a child value seen twice):", ""]
        lines += [f"- {d['part']}: {d['child']} → {d['parent']} ({d['reason']}): holds {d['held']}, lift "
                  f"{d['lift']}, supported {d['supported']}" for d in rejected]
    lines += ["", "## Identifiers, sensitive columns and time", ""]
    for p in f["parts"]:
        ids = [f"{i['column']} ({i['proposal']}" + (f", {i['check_digit']}" if i["check_digit"] else "") + ")"
               for i in p["identifiers"]]
        tagged = [f"{c['name']} ({c['sensitivity']})" for c in p["columns"] if c["sensitivity"] != "none"]
        t = p["time"]
        roles = [f"as of {t['as_of']['from']}–{t['as_of']['to']}" if t["as_of"]["from"] else "",
                 f"as at {t['as_at']}" if t["as_at"] else "", f"event {t['event_time']}" if t["event_time"] else "",
                 f"series by {', '.join(t['series']['key'])} every {t['series']['step']}" if t["series"] else ""]
        bits = [b for b in [("identifiers: " + ", ".join(ids)) if ids else "",
                            ("sensitive: " + ", ".join(tagged)) if tagged else "", ", ".join(r for r in roles if r)] if b]
        if bits:
            lines.append(f"- **{p['part']}**: " + "; ".join(bits))
    lines += ["", "## Data quality to hand to data-quality", ""]
    issues = [(p["part"], q) for p in f["parts"] for q in p["quality"]]
    lines += [f"- {part}: {q['check']}: {q['why']}" for part, q in issues] or ["None found."]
    lines += ["", "## Questions for the operator (one at a time)", ""]
    lines += [f"{i}. {q['question']} Recommendation: {q['recommendation']}" for i, q in enumerate(f["questions"], 1)] \
        or ["None."]
    lines += ["", "Samples of personal columns are masked to their shape. Store suggestions are advice only.", ""]
    return "\n".join(lines)
