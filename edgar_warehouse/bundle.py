"""The data skill's own commands: `doctor` and `skill install` (mastering to-do 21).

The skills ship inside the installed package, so an agent with no checkout of
this repository gets the same skills and commands. `doctor` checks that every
`edgar-warehouse` command and flag a skill names exists, that the configured
engine loads, where the rules folder is, and that each store whose address is
set answers. It never prints an address: they hold passwords.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import sys
from pathlib import Path

# Installed: the skills sit beside this module. In the repository: `skills/`.
_PACKAGED = Path(__file__).resolve().parent / "bundle_data" / "skills"
SKILLS = _PACKAGED if _PACKAGED.is_dir() else Path(__file__).resolve().parents[1] / "skills"
# The approved rules the bundle was built with: a folder to start from.
RULES = SKILLS.parent / "rules"
STORES = (
    "RULES_DATABASE_URL",
    "BOOKKEEPING_CLEAN_DATABASE_URL",
    "CHANGE_JOURNAL_DATABASE_URL",
    "MDM_DATABASE_URL",
)
# A fenced line or a code span may wrap onto the next line.
_COMMAND = re.compile(r"edgar-warehouse ([a-z][a-z-]*)([^`\n]*)")
# Written in a skill with a fallback, and marked "not built" there.
NOT_BUILT = {("rules", "profile"), ("rules", "check")}


def _choices(parser: argparse.ArgumentParser) -> dict:
    actions = [a for a in parser._actions if isinstance(a, argparse._SubParsersAction)]
    return actions[0].choices if actions else {}


def named_commands(root: Path = SKILLS) -> list[tuple[str, str, list[str]]]:
    """(file, group, the words after it) for every command line a skill writes."""
    found = []
    for path in sorted(root.rglob("*.md")):
        text = path.read_text(encoding="utf-8").replace("\\\n", " ")
        for group, rest in _COMMAND.findall(text):
            found.append((str(path.relative_to(root)), group, rest.split()))
    return found


def unresolved(parser: argparse.ArgumentParser, root: Path = SKILLS) -> list[str]:
    """Each command or flag a skill names that the command line does not have.

    The words after the group are followed down the subcommands while they
    name one; a flag must exist on the command reached. A placeholder
    (`<run-id>`) or a value is skipped.
    """
    groups, missing = _choices(parser), []
    for where, group, words in named_commands(root):
        if group not in groups:
            missing.append(f"{where}: edgar-warehouse {group}")
            continue
        target, path = groups[group], [group]
        for word in words:
            commands = _choices(target)
            if not commands or word.startswith(("-", "<")):
                break
            if (group, word) in NOT_BUILT and len(path) == 1:
                target = None
                break
            if word not in commands:
                missing.append(f"{where}: edgar-warehouse {' '.join(path)} {word}")
                target = None
                break
            target, path = commands[word], [*path, word]
        if target is None:
            continue
        missing.extend(
            f"{where}: edgar-warehouse {' '.join(path)} {flag}"
            for flag in re.findall(r"(?<![\w-])--[a-z0-9][a-z0-9-]*", " ".join(words))
            if flag != "--help" and flag not in target._option_string_actions
        )
    return sorted(set(missing))


def _store(variable: str) -> str:
    url = os.environ.get(variable)
    if not url:
        return "not set"
    from sqlalchemy import create_engine, text

    engine = create_engine(url, pool_pre_ping=True)
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return "answers"
    except Exception as exc:  # the address is never printed, only the failure's kind
        return f"does not answer ({type(exc).__name__})"
    finally:
        engine.dispose()


def doctor(parser: argparse.ArgumentParser) -> dict:
    from edgar_warehouse.rules import files

    try:
        import source_contract  # noqa: F401

        engine = "loads"
    except ImportError as exc:
        engine = f"missing ({exc})"
    report = {
        "skills": str(SKILLS),
        "commands_named": len(named_commands()),
        "unresolved": unresolved(parser),
        "engine": engine,
        "rules_root": {"path": str(files.ROOT), "exists": files.ROOT.is_dir()},
        "stores": {variable: _store(variable) for variable in STORES},
    }
    report["ok"] = (
        not report["unresolved"]
        and engine == "loads"
        and not any(state.startswith("does not") for state in report["stores"].values())
    )
    return report


def install(home: Path, rules: Path | None = None) -> list[str]:
    """Copy each bundled skill into the shared and Claude skill folders.

    A skill already there is replaced only when it is a copy this command made
    (it holds `.installed-by-edgar-warehouse`); anything else is refused.
    `rules`, when given, receives a copy of the bundled rules folder to start
    from; an existing folder is never overwritten.
    """
    done = []
    if rules is not None:
        if rules.exists():
            raise SystemExit(f"refusing to overwrite {rules}: copy the bundled rules into a new folder")
        shutil.copytree(RULES, rules)
        done.append(str(rules))
    for skill in sorted(p for p in SKILLS.iterdir() if (p / "SKILL.md").is_file()):
        for base in (home / ".agents" / "skills", home / ".claude" / "skills"):
            target = base / skill.name
            if target.is_symlink() or (target.exists() and not (target / ".installed-by-edgar-warehouse").is_file()):
                raise SystemExit(f"refusing to replace {target}: it was not installed by this command")
            if target.exists():
                shutil.rmtree(target)
            shutil.copytree(skill, target)
            (target / ".installed-by-edgar-warehouse").write_text(str(SKILLS) + "\n")
            done.append(str(target))
    return done


def register(subparsers, parser: argparse.ArgumentParser) -> None:
    _register_plan(subparsers)
    check = subparsers.add_parser("doctor", help="Check the skills' commands, the engine, the rules folder and the stores")
    check.set_defaults(handler=lambda _args: _print(doctor(parser)))
    skill = subparsers.add_parser("skill", help="The bundled skills")
    skill_commands = skill.add_subparsers(dest="skill_command", required=True)
    put = skill_commands.add_parser("install", help="Copy the bundled skills into ~/.agents/skills and ~/.claude/skills")
    put.add_argument("--home", default=str(Path.home()))
    put.add_argument("--rules", help="Also copy the bundled rules folder here (a new folder) to start from")
    put.set_defaults(handler=lambda args: _print(
        {"ok": True, "installed": install(Path(args.home), Path(args.rules) if args.rules else None)}))


def _resolve_feed(args) -> int:
    from edgar_warehouse.bookkeeping.clean.feeds import resolve_feed

    try:
        result = resolve_feed(Path(args.rules_root), args.source, args.feed)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(result, sort_keys=True, indent=2))
    return 0


def _plan_workflow(args) -> int:
    from edgar_warehouse.application.journal_evidence import plan
    from edgar_warehouse.bookkeeping.clean.config import canonical

    value = plan(source=args.source, feed=args.feed, target=args.target,
                 inputs={"uri": args.input_manifest, "sha256": args.input_sha256},
                 rules_root=Path(args.rules_root))
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(canonical(value) + "\n")
    print(json.dumps(value, indent=2, sort_keys=True))
    return 0


def _register_plan(subparsers) -> None:
    from edgar_warehouse.rules import files

    planning = subparsers.add_parser("plan", help="Read-only planning: resolve a feed, plan a workflow")
    steps = planning.add_subparsers(dest="plan_command", required=True)
    feed = steps.add_parser("resolve-feed", help="The Rules digest, datasets and targets of one source's feed")
    workflow = steps.add_parser("workflow", help="Plan one feed's frozen worklist from an input manifest; writes nothing else")
    for command in (feed, workflow):
        command.add_argument("--source", required=True)
        command.add_argument("--feed", required=True)
        command.add_argument("--rules-root", default=str(files.ROOT))
    feed.set_defaults(handler=_resolve_feed)
    workflow.add_argument("--target", required=True)
    workflow.add_argument("--input-manifest", required=True)
    workflow.add_argument("--input-sha256", required=True)
    workflow.add_argument("--output", required=True)
    workflow.set_defaults(handler=_plan_workflow)


def _print(report: dict) -> int:
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["ok"] else 1
