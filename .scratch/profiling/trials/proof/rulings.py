"""Profiling ticket 08: the rulings file the cold agent replays.

Every operator ruling recorded in a ticket or map under `.scratch/` (not in
trial logs or research notes, which hold answers) is harvested as written: the operator's exact words, the date, the ticket and line, and the
sentence around it (the question it answered). Nothing is paraphrased or
invented. Each entry is marked `"replayed": true` and `"valid_only_in":
"sandbox"`: a replayed ruling approves nothing outside the sandbox (plan
decision 29). The cold agent may only use a ruling from this file; a question it
does not answer is recorded by the agent as "unanswered, would ask the
operator" and listed in DIFF.md.

Rulings are written in many styles (`(operator, 2026-10-07: "Out of scope")`,
`The operator: "Approved" (2026-10-07 13:07 ET)`, a chosen option
`"Succession types (Recommended)"`, a table of names each "approved"). So each list
item, table row or paragraph is kept, whole and verbatim, with its section
heading, when it or its heading carries a date and either names the
operator or approves, chooses or rules, and quotes words or ticks a part. Over-
inclusion is safe (each line is the record itself, with its ticket and line);
a ruling written in no ticket is not in this file, and the agent asks.

    uv run --no-sync python .scratch/profiling/trials/proof/rulings.py
"""

from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
HERE = Path(__file__).resolve().parent
DATE = re.compile(r"20\d\d-\d\d-\d\d")
WHO = re.compile(r"operator|\(Recommended\)|approv|ruling|chose|switched on", re.I)
SAID = re.compile(r'["“][^"”\n]{1,400}["”]|^\s*[-|].*approv', re.I)


def blocks(lines: list[str]):
    """Each list item, table row or paragraph, verbatim (its lines joined by newlines),
    with its first line number and section heading. Fenced code is skipped."""
    heading, start, block, fenced = "", 0, [], False
    for number, line in enumerate(lines + [""], 1):
        if line.lstrip().startswith("```"):
            fenced = not fenced
            continue
        if fenced:
            continue
        new = (not line.strip() or line.startswith("#")
               or re.match(r"\s{0,1}[-|*]\s|\s{0,1}\|-|\d+\.\s", line))
        if new and block:
            yield start, heading, "\n".join(block)
            block = []
        if line.startswith("#"):
            heading = line.lstrip("# ").strip()
        elif line.strip():
            start = number if not block else start
            block.append(line)


def main() -> None:
    rulings, seen = [], set()
    for path in sorted((ROOT / ".scratch").rglob("*.md")):
        # Trial logs and research notes hold answers and findings, not rulings.
        if HERE in path.parents or {"trials", "research"} & set(path.relative_to(ROOT).parts):
            continue
        rel = str(path.relative_to(ROOT))
        for number, heading, text in blocks(path.read_text(errors="replace").splitlines()):
            dates = DATE.findall(text) or DATE.findall(heading)
            if not dates or not (WHO.search(text) or WHO.search(heading)) or not SAID.search(text):
                continue
            if text in seen:
                continue
            seen.add(text)
            rulings.append({"first_date": dates[0], "section": heading, "text": text, "ticket": rel, "line": number,
                            "replayed": True, "valid_only_in": "sandbox"})
    rulings.sort(key=lambda r: (r["first_date"], r["ticket"], r["line"]))
    with (HERE / "rulings.jsonl").open("w") as f:
        for ruling in rulings:
            f.write(json.dumps(ruling, ensure_ascii=False) + "\n")
    by_map = {}
    for ruling in rulings:
        name = ruling["ticket"].split("/")[1]
        by_map[name] = by_map.get(name, 0) + 1
    print(json.dumps({"rulings": len(rulings), "by_map": dict(sorted(by_map.items()))}, indent=1))


if __name__ == "__main__":
    main()
