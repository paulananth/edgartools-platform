"""Trial of ticket 01c: each trial's defects become checks that load, count what profiling counted, and fire.

    uv run --extra mdm python .scratch/profiling/trials/quality_trial.py <out> --input name=path [...]

Profiles the inputs with the current code (keeping the run's working database
until the end), then, for every part with quality items:
- maps each column a check needs to `fields.<column as lower-case words>`;
- drafts the quality block with the data-quality helper, writes it, and
  loads it back as the rules loader does, checked as registration checks it;
- builds one record per row of the part (values as text) and runs the block
  with the engine's quality.apply;
- compares each check's count with profiling's, and fires a planted record
  per check;
- checks that every marked invalid row has a fix with its evidence, or needs
  a steward.

The findings are marked approved for this trial only ("trial: not an operator
approval"): the helper refuses unapproved findings. The working database is
deleted at the end. Writes RESULT-quality.md and per-part quality.yaml files.
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
import tempfile
from pathlib import Path

import duckdb
import yaml

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "skills" / "data-profiling" / "scripts"))
sys.path.insert(0, str(ROOT / "skills" / "data-quality" / "scripts"))
from profiling import inputs, report, run  # noqa: E402

import quality_plan  # noqa: E402


def field(column: str) -> str:
    words = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", column)
    return "fields." + (re.sub(r"[^a-z]+", "_", words.lower()).strip("_") or "value")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("out", type=Path)
    parser.add_argument("--input", action="append", required=True)
    parser.add_argument("--name", default="trial")
    args = parser.parse_args()
    sources = dict(i.split("=", 1) for i in args.input)
    args.out.mkdir(parents=True, exist_ok=True)
    work = Path(tempfile.mkdtemp(prefix="quality-trial-", dir=args.out))
    try:
        findings = run.profile_inputs(sources, args.name, work=work)
        report.write(findings, args.out)
        findings["approval"] = {"status": "approved", "approved_by": "trial",
                                "approved_words": "trial: not an operator approval", "approved_at": run.now()}
        con = duckdb.connect(str(work / "profile.duckdb"), read_only=True)
        lines = ["| Part | Defects | Became checks or fixes | Counts equal | Planted fire | New code |",
                 "|---|---|---|---|---|---|"]
        details, failures, defects, carried = [], 0, 0, 0
        for part in findings["parts"]:
            if not part["quality"]:
                continue
            columns = {i["column"] for i in part["quality"] if i["column"]}
            fields = {c: field(c) for c in columns}
            if len(set(fields.values())) < len(fields):
                fields = {c: f"{p}_{chr(97 + n % 26) * (1 + n // 26)}" for n, (c, p) in enumerate(sorted(fields.items()))}
            plan = quality_plan.draft(findings, part["part"], fields, f"{args.name}-{part['part']}-quality-trial")
            folder = args.out / "quality" / part["part"]
            folder.mkdir(parents=True, exist_ok=True)
            code = re.sub(r"[^a-z0-9]+", "_", part["part"].lower())
            reasons = quality_plan.loads(quality_plan.write(plan, code, folder / "quality.yaml"), code)
            (folder / "QUALITY.md").write_text(quality_plan.report(plan), encoding="utf-8")
            wanted = sorted(fields)
            select = ", ".join(f"CAST({inputs.sql_name(c)} AS VARCHAR)" for c in wanted)
            counts = {i["id"]: 0 for i in [*(plan["block"].get("fixes") or []), *plan["block"]["checks"]]}
            cursor = con.execute(f"SELECT {select} FROM {inputs.sql_name(part['part'])}") if counts else None
            while cursor and (batch := cursor.fetchmany(50_000)):  # millions of rows: measured a batch at a time
                for check_id, n in quality_plan.measure(
                        plan["block"], [quality_plan.mapped(dict(zip(wanted, row)), fields) for row in batch]).items():
                    counts[check_id] += n
            planted = quality_plan.planted_fire(plan["block"])
            equal = [k for k, v in plan["expected"].items() if counts[k] == v]
            failures += len(plan["expected"]) - len(equal) + sum(v is False for v in planted.values()) \
                + len(plan["unmapped"])
            defects += len(part["quality"])
            carried += len(plan["expected"])
            lines.append(f"| {part['part']} | {len(part['quality'])} | {len(plan['expected'])} | "
                         f"{len(equal)} of {len(plan['expected'])} | {sum(v is True for v in planted.values())} of "
                         f"{len(planted)} | {', '.join(sorted({i['check'] for i in plan['new_code']})) or '-'} |")
            details += [f"- {part['part']}.{k}: profiling {plan['expected'][k]}, engine {counts[k]}"
                        for k in plan["expected"] if counts[k] != plan["expected"][k]]
        con.close()
        rows = [json.loads(line) for line in (args.out / "invalid_rows.jsonl").open()]
        unsupported = [r for r in rows if not ((r["fix"] is not None and r["fix_evidence"]) or r["needs_steward"])]
        failures += len(unsupported)
        fixed = sum(r["fix"] is not None for r in rows)
        body = ["# Quality trial", "", f"{args.name}: profiled with the current code; findings approved for this "
                "trial only.", "", *lines, "",
                f"{carried} of {defects} defects became engine checks or fixes; the rest are new code, each "
                "with what its check would test (QUALITY.md per part). A code-list guard counts 0 on its own "
                "delivery by design: its planted record proves it fires.", "",
                f"Invalid hierarchy rows marked: {len(rows)}; {fixed} with an evidence-backed fix, "
                f"{len(rows) - fixed} for a steward; {len(unsupported)} without either.", "",
                f"**{'Every check loads, counts what profiling counted, and fires.' if not failures else f'{failures} failures'}**",
                *([""] + details if details else [])]
        (args.out / "RESULT-quality.md").write_text("\n".join(body) + "\n", encoding="utf-8")
        print("\n".join(body))
        return 1 if failures else 0
    finally:
        shutil.rmtree(work, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
