"""The try page for one family.

A family is a file named ``bench_families/<name>.py``. It declares ``title``
and ``inputs``. Each input is ``{"name", "label"}``. When the family can be
tried, ``run(inputs, rule)`` returns one JSON object.

``<name>_full.py`` is loaded only when ``<name>.py`` is there too. It may
declare ``words``, a list of ``{"word", "stored"}``, and ``explain(rule)``
for Show the full rule. A short-word file with no family file is ignored.
"""

from __future__ import annotations

import html
import importlib.util
import json
from pathlib import Path

FAMILY_DIR = Path(__file__).resolve().parent / "bench_families"

BUTTONS = ("Try", "Show the full rule", "Keep a copy", "Store this draft")


class MissingFamily(Exception):
    """The named family file is not in the folder."""


def families(directory: Path | None = None) -> list[str]:
    """Family names, from the files in the folder. Short-word files are not families."""
    folder = _folder(directory)
    if not folder.is_dir():
        return []
    names = []
    for path in folder.glob("*.py"):
        stem = path.stem
        if stem.startswith("_") or stem.endswith("_full"):
            continue
        names.append(stem)
    return sorted(names)


def matches(actual, expected) -> bool:
    """JSON equality. Key order is ignored. List order counts."""
    return _json(actual) == _json(expected)


def build_case(family: str, rule: str, inputs: dict, expected, actual) -> dict:
    return {
        "family": family,
        "rule": rule,
        "inputs": inputs,
        "expected": expected,
        "actual": actual,
        "passed": matches(actual, expected),
    }


def load_full(name: str, directory: Path | None = None):
    """The short-word module, or None when the family file is absent."""
    folder = _folder(directory)
    _check_name(name)
    if not _family_path(name, folder).is_file():
        return None
    path = folder / f"{name}_full.py"
    if not path.is_file():
        return None
    return _load(path)


def attempt(name: str, rule: str, inputs: dict, directory: Path | None = None) -> dict:
    """Try the pasted rule. A family with no ``run`` refuses."""
    family = load_family(name, directory)
    run = getattr(family, "run", None)
    if not callable(run):
        return {"refused": "This family cannot be tried yet."}
    result = run(inputs, rule)
    if not isinstance(result, dict):
        return {"refused": "The result is not one JSON object."}
    return result


def show_full(name: str, rule: str, directory: Path | None = None) -> dict:
    """The stored key beside each typed word, or a refusal."""
    folder = _folder(directory)
    _check_name(name)
    if not _family_path(name, folder).is_file():
        raise MissingFamily(f"No family named {name}.")
    full = load_full(name, directory)
    if full is None:
        return {"refused": "This family has no short words yet."}
    explain = getattr(full, "explain", None)
    if callable(explain):
        result = explain(rule)
        if not isinstance(result, dict):
            return {"refused": "The result is not one JSON object."}
        return result
    words = getattr(full, "words", None)
    if not isinstance(words, list):
        return {"refused": "This family has no short words yet."}
    return {"lines": list(words)}


def present(name: str, directory: Path | None = None) -> str:
    """The page: the family's title and inputs, the rule, and the expected output."""
    family = load_family(name, directory)
    title = getattr(family, "title", None)
    declared = getattr(family, "inputs", None)
    if not isinstance(title, str) or not _inputs_ok(declared):
        raise MissingFamily(f"The family {name} does not declare a title and inputs.")
    full = load_full(name, directory)
    words = []
    if full is not None and isinstance(getattr(full, "words", None), list):
        words = list(full.words)
    return _page(title, declared, words)


def press(button: str, name: str, *, rule: str = "", inputs: dict | None = None,
          expected=None, path: Path | None = None, directory: Path | None = None) -> dict:
    """Press one of the four buttons. The result is one JSON object."""
    if button not in BUTTONS:
        return {"refused": "That button is not on the page."}
    pasted = dict(inputs or {})
    if button == "Try":
        return _tried(name, rule, pasted, expected, directory)
    if button == "Show the full rule":
        return show_full(name, rule, directory)
    case = _case_for_save(name, rule, pasted, expected, directory)
    if button == "Keep a copy":
        from .bench_keep import keep_copy
        return keep_copy(case, path)
    from .bench_store import store_draft
    return store_draft(case)


def load_family(name: str, directory: Path | None = None):
    folder = _folder(directory)
    _check_name(name)
    path = _family_path(name, folder)
    if not path.is_file():
        raise MissingFamily(f"No family named {name}.")
    return _load(path)


def _tried(name: str, rule: str, inputs: dict, expected, directory: Path | None) -> dict:
    actual = attempt(name, rule, inputs, directory)
    if set(actual) == {"refused"}:
        return actual
    return build_case(name, rule, inputs, expected, actual)


def _case_for_save(name: str, rule: str, inputs: dict, expected, directory: Path | None) -> dict:
    actual = attempt(name, rule, inputs, directory)
    if set(actual) == {"refused"}:
        actual = None
    return build_case(name, rule, inputs, expected, actual)


def _page(title: str, declared: list[dict], words: list) -> str:
    fields = []
    for item in declared:
        ident = html.escape(item["name"], quote=True)
        label = html.escape(item["label"], quote=True)
        fields.append(
            f'<p><label for="input-{ident}">{label}</label>'
            f'<textarea id="input-{ident}" name="{ident}"></textarea></p>'
        )
    shown = []
    for item in words:
        if isinstance(item, dict) and isinstance(item.get("word"), str) and isinstance(item.get("stored"), str):
            shown.append(
                f'<li>{html.escape(item["word"])} {html.escape(item["stored"])}</li>'
            )
    word_list = f"<ul>{''.join(shown)}</ul>" if shown else ""
    buttons = "".join(f"<button type=\"button\">{html.escape(name)}</button>" for name in BUTTONS)
    safe_title = html.escape(title, quote=True)
    return (
        "<!DOCTYPE html>\n"
        "<html lang=\"en\">\n"
        f"<head><meta charset=\"utf-8\"><title>{safe_title}</title></head>\n"
        "<body>\n"
        f"<h1>{safe_title}</h1>\n"
        f"{''.join(fields)}\n"
        "<p><label for=\"rule\">Rule</label><textarea id=\"rule\" name=\"rule\"></textarea></p>\n"
        "<p><label for=\"expected\">Expected output</label>"
        "<textarea id=\"expected\" name=\"expected\"></textarea></p>\n"
        f"<p>{buttons}</p>\n"
        f"{word_list}\n"
        "</body>\n"
        "</html>\n"
    )


def _inputs_ok(declared) -> bool:
    if not isinstance(declared, list):
        return False
    for item in declared:
        if not isinstance(item, dict):
            return False
        name = item.get("name")
        label = item.get("label")
        if not isinstance(name, str) or not isinstance(label, str) or not name or not label:
            return False
        if Path(name).name != name:
            return False
    return True


def _folder(directory: Path | None) -> Path:
    return FAMILY_DIR if directory is None else Path(directory)


def _family_path(name: str, folder: Path) -> Path:
    return folder / f"{name}.py"


def _check_name(name: str) -> None:
    if (not isinstance(name, str) or not name or name.startswith("_") or name.endswith("_full")
            or Path(name).name != name or "/" in name or "\\" in name):
        raise MissingFamily(f"No family named {name}.")


def _load(path: Path):
    spec = importlib.util.spec_from_file_location(f"rules_try_{path.stem}", path)
    if spec is None or spec.loader is None:
        raise MissingFamily(f"No family named {path.stem.removesuffix('_full')}.")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _json(value) -> str:
    return json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False)
