#!/usr/bin/env python3
"""Move whole sections of a skill's SKILL.md into a sibling file, leaving each heading with a pointer.

Usage: move_skill_section.py <skill folder> <target.md> <title> <heading>=<pointer> [<heading>=<pointer> ...]

A section runs from its heading to the next heading of the same or a higher level (fenced code
is skipped). The heading stays in SKILL.md, so links to its anchor still land, followed by the
pointer. The move is checked: every line SKILL.md held is in SKILL.md or the target afterwards.
"""
import collections
import pathlib
import re
import sys

HEADING = re.compile(r"^(#{1,6}) ")


def section(lines, heading):
    start = lines.index(heading)
    level, fenced = len(HEADING.match(heading).group(1)), False
    for end in range(start + 1, len(lines)):
        if lines[end].startswith("```"):
            fenced = not fenced
        found = None if fenced else HEADING.match(lines[end])
        if found and len(found.group(1)) <= level:
            return start, end
    return start, len(lines)


def main(folder, target, title, *moves):
    skill = pathlib.Path(folder) / "SKILL.md"
    before = skill.read_text(encoding="utf-8").splitlines()
    lines, moved = list(before), []
    for move in moves:
        heading, pointer = move.split("=", 1)
        start, end = section(lines, heading)
        body = lines[start:end]
        while body and not body[-1].strip():
            body.pop()
        moved += body + [""]
        lines[start:end] = [heading, "", pointer, ""]
    name = pathlib.Path(folder).name
    out = pathlib.Path(folder) / target
    assert not out.exists(), f"{out} exists"
    out.write_text("\n".join([f"# {title}", "", f"Part of the `{name}` skill: [SKILL.md](SKILL.md) says when to read this.", ""]
                             + moved).rstrip("\n") + "\n", encoding="utf-8")
    skill.write_text("\n".join(lines).rstrip("\n") + "\n", encoding="utf-8")
    after = collections.Counter(l for l in lines + out.read_text(encoding="utf-8").splitlines() if l.strip())
    lost = collections.Counter(l for l in before if l.strip()) - after
    assert not lost, f"lines lost: {list(lost)[:5]}"
    print(f"{skill}: {len(before)} -> {len(lines)} lines; {out}: {len(moved) + 4} lines; no line lost")


if __name__ == "__main__":
    main(*sys.argv[1:])
