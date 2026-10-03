"""The data skill's own commands: `doctor` and `skill install` (mastering to-do 21).

The skills ship inside the installed package, so an agent with no checkout of
this repository gets the same skills and commands. `doctor` is the skills
checking themselves: every `edgar-warehouse` command, argument and flag a skill
writes exists, every relative link resolves, the configured engine loads, and
each store whose address is set answers. It never prints an address: they
hold passwords.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
from pathlib import Path

from edgar_warehouse.rules import files

# Installed: the skills (each carries the documents it links to) sit in `bundle_data`.
# In the repository: `skills/`.
SKILLS = files.BUNDLE_DATA / "skills" if files.BUNDLED.is_dir() else Path(__file__).resolve().parents[1] / "skills"
# The approved rules the bundle was built with: a folder to start from.
RULES = files.BUNDLED if files.BUNDLED.is_dir() else Path(__file__).resolve().parents[1] / "rules"
STORES = (
    "RULES_DATABASE_URL",
    "BOOKKEEPING_CLEAN_DATABASE_URL",
    "CHANGE_JOURNAL_DATABASE_URL",
    "MDM_DATABASE_URL",
)
MARKER = ".installed-by-edgar-warehouse"
# A fenced line or a code span may wrap onto the next line. A pipe ends the
# command: what follows is another program's.
_COMMAND = re.compile(r"edgar-warehouse ([a-z][a-z-]*)([^`\n|]*)")
# Only an installed command is portable; these work in a checkout alone.
_CHECKOUT_ONLY = re.compile(r"python -m edgar_warehouse|skills/[a-z-]+/scripts/")
_LINK = re.compile(r"\]\(([^)#\s]+)")
# Written in a skill with a fallback, and marked "not built" there.
NOT_BUILT = {("rules", "profile"), ("rules", "check")}


def _choices(parser: argparse.ArgumentParser) -> dict:
    actions = [a for a in parser._actions if isinstance(a, argparse._SubParsersAction)]
    return actions[0].choices if actions else {}


def _positionals(parser: argparse.ArgumentParser) -> list:
    return [a for a in parser._actions if not a.option_strings and not isinstance(a, argparse._SubParsersAction)]


def named_commands(root: Path = SKILLS) -> list[tuple[str, str, list[str]]]:
    """(file, group, the words after it) for every command line a skill writes."""
    found = []
    for path in sorted(root.rglob("*.md")):
        text = path.read_text(encoding="utf-8").replace("\\\n", " ")
        for group, rest in _COMMAND.findall(text):
            found.append((str(path.relative_to(root)), group, rest.split()))
    return found


def _command(where: str, group: str, words: list[str], groups: dict) -> list[str]:
    """What is wrong with one command line: a subcommand, a choice or a flag."""
    if group not in groups:
        return [f"{where}: edgar-warehouse {group}"]
    target, path, rest = groups[group], [group], list(words)
    while rest and _choices(target) and not rest[0].startswith(("-", "<", "$", '"')):
        word = rest.pop(0)
        if (group, word) in NOT_BUILT and len(path) == 1:
            return []
        if word not in _choices(target):
            return [f"{where}: edgar-warehouse {' '.join(path)} {word}"]
        target, path = _choices(target)[word], [*path, word]
    missing = []
    bare = [w for w in rest if not w.startswith("-")]
    for action, word in zip(_positionals(target), bare):
        # A placeholder (`<profile>`) or a variable stands for any value; a
        # written choice, or each of `a|b`, must be one the command takes.
        if action.choices and not word.startswith(("<", "$", '"')):
            missing += [f"{where}: edgar-warehouse {' '.join(path)} {choice}"
                        for choice in word.split("|") if choice not in action.choices]
    missing += [f"{where}: edgar-warehouse {' '.join(path)} {flag}"
                for flag in re.findall(r"(?<![\w-])--[a-z0-9][a-z0-9-]*", " ".join(rest))
                if flag != "--help" and flag not in target._option_string_actions]
    return missing


def unresolved(parser: argparse.ArgumentParser, root: Path = SKILLS) -> list[str]:
    """Each command, argument, flag or relative link a skill writes that does not exist."""
    groups = _choices(parser)
    missing = [problem for where, group, words in named_commands(root)
               for problem in _command(where, group, words, groups)]
    for path in sorted(root.rglob("*.md")):
        where = str(path.relative_to(root))
        text = path.read_text(encoding="utf-8")
        missing += [f"{where}: checkout-only command {m.group(0)!r}" for m in _CHECKOUT_ONLY.finditer(text)]
        missing += [f"{where}: link {link}" for link in _LINK.findall(text)
                    if "://" not in link and not (path.parent / link).exists()]
    return sorted(set(missing))


def _store(variable: str) -> str:
    url = os.environ.get(variable)
    if not url:
        return "not set"
    from sqlalchemy import create_engine, text

    engine = None
    try:
        engine = create_engine(url, connect_args={"connect_timeout": 5})
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return "answers"
    except Exception as exc:  # the address is never printed, only the failure's kind
        return f"does not answer ({type(exc).__name__})"
    finally:
        if engine is not None:
            engine.dispose()


def doctor(parser: argparse.ArgumentParser) -> dict:
    try:
        from edgar_warehouse.rules import source_engine  # noqa: F401  (the engine's one facade)

        engine = "loads"
    except ImportError as exc:
        engine = f"missing ({exc})"
    report = {
        "skills": str(SKILLS),
        "commands_named": len(named_commands()),
        "unresolved": unresolved(parser),
        "engine": engine,
        "rules_root": {"path": str(files.ROOT), "exists": files.ROOT.is_dir(),
                       # Readable, never written: set EDGAR_RULES_ROOT before any change.
                       "bundled_read_only": files.ROOT.resolve().is_relative_to(files.BUNDLE_DATA)},
        "stores": {variable: _store(variable) for variable in STORES},
    }
    report["ok"] = (
        not report["unresolved"]
        and engine == "loads"
        and report["rules_root"]["exists"]
        and not any(state.startswith("does not") for state in report["stores"].values())
    )
    return report


def _tree(folder: Path) -> str:
    """One digest of a folder's files, the marker left out."""
    digest = hashlib.sha256()
    for path in sorted(p for p in folder.rglob("*") if p.is_file() and p.name != MARKER):
        digest.update(str(path.relative_to(folder)).encode() + b"\0" + path.read_bytes() + b"\0")
    return digest.hexdigest()


def install(home: Path, rules: Path | None = None) -> list[str]:
    """Copy each bundled skill into the shared and Claude skill folders.

    Every target is checked before anything is written, so a refusal leaves
    nothing half-installed. A skill already there is replaced only when this
    command made it and nobody has changed it since (its marker holds the
    digest it was installed with). `rules`, when given, receives a copy of the
    bundled rules folder to start from; an existing folder is never overwritten.
    """
    skills = sorted(p for p in SKILLS.iterdir() if (p / "SKILL.md").is_file())
    targets = [(skill, base / skill.name) for skill in skills
               for base in (home / ".agents" / "skills", home / ".claude" / "skills")]
    refused = []
    if rules is not None and rules.exists():
        refused.append(f"{rules} exists: copy the bundled rules into a new folder")
    for _, target in targets:
        if target.is_symlink() or (target.exists() and not (target / MARKER).is_file()):
            refused.append(f"{target} was not installed by this command (remove it, or keep it)")
        elif target.exists() and (target / MARKER).read_text().split()[0] != _tree(target):
            refused.append(f"{target} was changed after it was installed (move the changes out first)")
    if refused:
        raise SystemExit("refusing to install:\n" + "\n".join(refused))
    done = []
    if rules is not None:
        shutil.copytree(RULES, rules)
        done.append(str(rules))
    for skill, target in targets:
        if target.exists():
            shutil.rmtree(target)
        shutil.copytree(skill, target)
        (target / MARKER).write_text(f"{_tree(target)} {SKILLS}\n")
        done.append(str(target))
    return done


def register(subparsers, parser: argparse.ArgumentParser) -> None:
    check = subparsers.add_parser("doctor", help="Check the skills' commands and links, the engine, the rules folder and the stores")
    check.set_defaults(handler=lambda _args: _print(doctor(parser)))
    skill = subparsers.add_parser("skill", help="The bundled skills")
    skill_commands = skill.add_subparsers(dest="skill_command", required=True)
    put = skill_commands.add_parser("install", help="Copy the bundled skills into ~/.agents/skills and ~/.claude/skills")
    put.add_argument("--home", default=str(Path.home()))
    put.add_argument("--rules", help="Also copy the bundled rules folder here (a new folder) to start from")
    put.set_defaults(handler=lambda args: _print(
        {"ok": True, "installed": install(Path(args.home), Path(args.rules) if args.rules else None)}))


def _print(report: dict) -> int:
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["ok"] else 1
