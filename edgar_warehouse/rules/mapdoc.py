"""The Mapping Document: a spreadsheet generated from the rules (rules skill
ticket 11).

One workbook per source that feeds MDM (`rules/sources/<source>/MAPPING.xlsx`)
and one per kind (`rules/merge/kinds/<kind>.xlsx`). Every sheet but Notes is
generated from the rules; stewards change it, `diff` prints what they
changed, cell by cell, and Claude turns that into the rules. The Notes sheet
is the stewards' own and is kept as written when the workbook is regenerated.
`check` fails when a workbook differs from what its rules generate, so the
two cannot drift.

Operator, 2026-09-28: "Initially, machine-generated must be able to edit and
update by stewards in an easily understandable way for humans".
"""

from __future__ import annotations

import difflib
import io
import json
import re
import zipfile
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any

from . import files

NOTES = "Notes"
NOTES_HEADER = ["Note", "About", "Who", "When"]
MAX_LISTED = 12  # longer lists show as a count, and the rules file holds them
# A fixed save time, so a workbook regenerated from unchanged rules is the same file.
SAVED_AT = datetime(2026, 1, 1)
_STAMP = SAVED_AT.strftime("%Y-%m-%dT%H:%M:%SZ").encode()

HOW_TO_CHANGE = (
    "Generated from the rules. To change a rule, change its cell here, then run "
    "`edgar-warehouse rules mapdoc diff`; Claude turns the change into the rules, "
    "and it acts only once its rules version is approved. Write your own notes on "
    "the Notes sheet: they are kept."
)

# What each data quality fix and test does, in plain words. A test holds every
# name in quality.CHECKS and quality.FIXES here.
QUALITY_WORDS = {
    "blank_values@1": "Empties a value the source writes wrongly: {values}",
    "name_state_marker@1": "Fills an empty {target} from the US state tag at the end of the name (\"/DE\")",
    "standardize_address@1": "Keeps a copy for matching only: upper case, USPS street words, no suite, 5-digit ZIP",
    "present@1": "The value is filled",
    "in_set@1": "The value is one of: {values}",
    "pattern@1": "The value matches {regex}",
    "lei_check_digit@1": "The LEI check digits pass",
    "placeholder@1": "The value is not a placeholder: {values}",
    "registered_agent_address@1": "The address is not a registered agent's: {markers}",
    "in_reference@1": "The value is in the reference table {table}",
}
ON_FAIL_WORDS = {
    "exception": "Exception: the record never merges and never stops the run; fix or ignore it",
    "withhold": "Withheld: kept on the record, never used to match",
    "flag": "Counted only",
}
# What each matching and classification condition checks, in plain words.
CONDITION_WORDS = {
    "field_in_set@1": "{field} is one of: {values}",
    "fields_all_empty@1": "{fields} is empty",
    "token_match@2": "{field} holds at least {min_count} word(s) of the list {token_list}",
    "values_overlap@1": "{field} holds at least {min_count} of the list {values}",
    "evidence_present@1": "The record has {document}",
    "name_census_match@1": "The names are equal, legal form kept, and exactly one SEC filer and one GLEIF "
                           "entity carry that name",
    "gleif_entity_eligible@1": "The GLEIF entity is {categories}, {entity_statuses}, and not "
                               "{refused_registration_statuses}",
    "holds_no_other_lei@1": "The SEC company is not already linked to another LEI",
    "jurisdiction_agrees@1": "SEC's {sec_field} names the same place as GLEIF's {gleif_field}",
    "jurisdictions_do_not_conflict@1": "SEC's {sec_field} and GLEIF's {gleif_field} do not name different places",
    "postal_agrees@1": "SEC's business postcode equals GLEIF's headquarters postcode, in the same country",
}


def _text(value: Any) -> str:
    """One cell's text: every generated cell is text, so it reads back the same.
    A list longer than MAX_LISTED shows as a count."""
    if value is None:
        return ""
    if isinstance(value, list):
        if len(value) > MAX_LISTED:
            return f"{len(value)} values (see the rules file)"
        return ", ".join(_text(v) for v in value)
    if isinstance(value, dict):
        return "; ".join(f"{k}: {_text(v)}" for k, v in value.items())
    return str(value)


def _words(table: dict, name: str, args: dict) -> str:
    """Plain words for a named test, fix or condition; its code if it has none."""
    template = table.get(name)
    if template is None:
        return f"{name} {_text(args)}".strip()
    return template.format_map(defaultdict(str, {k: _text(v) for k, v in (args or {}).items()}))


def _paths(spec: Any) -> list[tuple[str, str]]:
    """(part, source path) for one mapped value: a path, or an address's parts."""
    if isinstance(spec, str):
        return [("", spec)]
    parts = []
    for part, path in (spec.get("components") or {}).items():
        if isinstance(path, dict) and "lines" in path:
            path = f"{path['lines']} (lines)"
        parts.append((part, _text(path)))
    return parts


def _kind_of(adapter: dict) -> str:
    if adapter.get("kind"):
        return adapter["kind"]
    if adapter.get("kind_values"):
        return "by category: " + _text(adapter["kind_values"])
    return _text((adapter.get("classification") or {}).get("kind"))


def _winners(policy: dict, root: Path) -> dict[str, dict[str, tuple[list[str], list[str]]]]:
    """kind -> MDM field -> (the datasets that fill it, first wins; the sheet
    row: those datasets, the winner, which rule orders them, its path), as
    the merge engine picks a winner
    (`survivorship._select_values`): a field with its own rule
    (`fields.<name>`) takes the kind's `defaults` and changes any part of
    it, its source order included; every other field takes the default."""
    filled: dict[str, set] = defaultdict(set)
    for path in sorted((root / "sources").glob("*/source.yaml")):
        for code, entry in (files.load_source(path).get("mdm") or {}).items():
            for field in ((entry.get("contract") or {}).get("adapter") or {}).get("fields") or {}:
                filled[field].add(code)
    found: dict[str, dict] = {}
    for kind, rules in (policy.get("kinds") or {}).items():
        defaults = rules.get("defaults") or {}
        own = rules.get("fields") or {}
        found[kind] = {}
        for field in sorted(set(filled) | set(own)):
            rule = {**defaults, **own.get(field, {})}
            order = rule.get("sources") or []
            sources = [c for c in order if c in filled.get(field, set())]
            if not sources and field not in own:
                continue  # no source of this kind fills it
            if field in own:
                extra = {k: v for k, v in own[field].items() if k != "sources"}
                which = "Its own rule" + (f" ({_text(extra)})" if extra else "")
                at = f"merge/kinds/{kind}.yaml fields.{field}"
                if "sources" not in own[field]:  # its order is still the kind's
                    which += ", order from the kind default"
                    at += f"; merge/kinds/{kind}.yaml defaults.sources"
            else:
                which, at = "Kind default", f"merge/kinds/{kind}.yaml defaults.sources"
            found[kind][field] = (sources, [_text(sources), sources[0] if sources else "", which, at])
    return found


# --- a source's workbook ----------------------------------------------------------

def _source_sheets(name: str, body: dict, policy: dict, root: Path) -> dict[str, list[list[str]]]:
    about = [["What", "Value"], ["How to change this", HOW_TO_CHANGE], ["Source", name],
             ["Captured files (bronze family)", _text((body.get("bronze") or {}).get("family"))]]
    fields = [["Dataset", "MDM field", "Part", "Source path", "Used for", "Rules path"]]
    identifiers = [["Dataset", "Identifier", "Source path", "Format", "Joins records into one",
                    "Can it change", "Rules path"]]
    critical = [["Dataset", "MDM field", "Test", "When it fails", "Rules path"]]
    quality = [["Dataset", "Id", "Fix or check", "What it does", "Reads", "When it fails", "Rules path"]]
    wins = [["Kind", "MDM field", "Filled by, first wins", "Winner", "Rule", "Rules path"]]
    from edgar_warehouse.mdm.clean.activation import NAMESPACES  # the identifiers that join records

    winners = _winners(policy, root)
    for code, entry in (body.get("mdm") or {}).items():
        contract = entry.get("contract") or {}
        adapter = contract.get("adapter") or {}
        at = f"mdm.{code}.contract"
        about += [
            [f"{code}: provider", _text(contract.get("provider"))],
            [f"{code}: kind", _kind_of(adapter)],
            [f"{code}: one record is", _text(contract.get("record_key"))],
            [f"{code}: one publication is", _text(contract.get("publication_key"))],
            [f"{code}: a file covers", _text(contract.get("completeness") or contract.get("semantics"))],
            [f"{code}: set aside without stopping the run", _text(contract.get("nonblocking_deferred_reasons"))],
        ]
        for section, used_for in (("fields", "MDM field"), ("matching", "Matching only")):
            for field, spec in (adapter.get(section) or {}).items():
                for part, path in _paths(spec):
                    fields.append([code, field, part, path, used_for, f"{at}.adapter.{section}.{field}"])
        for relationship in adapter.get("relationships") or []:
            kinds = relationship.get("type") or _text(list((relationship.get("type_values") or {}).values()))
            fields.append([code, f"relationship {kinds}", "to", _text(relationship.get("target_key")),
                           f"Link to {_text(relationship.get('target_source'))}", f"{at}.adapter.relationships"])
        formats = adapter.get("identifier_formats") or {}
        for ident, path in (adapter.get("identifiers") or {}).items():
            identifiers.append([code, ident, _text(path), _text(formats.get(ident)),
                                "Yes" if ident in NAMESPACES else "No: lookup only",
                                "Only with a new dataset code", f"{at}.adapter.identifiers.{ident}"])
        block = contract.get("quality") or {}
        for i, fix in enumerate(block.get("fixes") or []):
            args = fix.get("args") or {}
            quality.append([code, _text(fix.get("id")), "Fix", _words(QUALITY_WORDS, fix.get("fix"), args),
                            _text(args.get("field") or args.get("name")), "", f"quality.{code}.fixes[{i}]"])
        for i, check in enumerate(block.get("checks") or []):
            args = check.get("args") or {}
            words = _words(QUALITY_WORDS, check.get("test"), args)
            fails = ON_FAIL_WORDS.get(check.get("on_fail"), _text(check.get("on_fail")))
            quality.append([code, _text(check.get("id")), "Check", words, _text(check.get("value")), fails,
                            f"quality.{code}.checks[{i}]"])
            if check.get("on_fail") == "exception":  # a critical data element
                critical.append([code, _text(check.get("value")).removeprefix("fields."), words, fails,
                                 f"quality.{code}.checks[{i}]"])
        for kind, by_field in winners.items():
            for field, (sources, row) in by_field.items():
                if code in sources:
                    wins.append([kind, field, *row])
    return {"Source": about, "Fields": fields, "Identifiers": identifiers,
            "Critical data elements": critical, "Data quality": quality, "Who wins": wins}


# --- a kind's workbook --------------------------------------------------------------

def _conditions(items: list[dict]) -> str:
    return "; and ".join(_words(CONDITION_WORDS, w.get("primitive"), w.get("args") or {}) for w in items)


def _kind_sheets(kind: str, rules: dict, by_field: dict[str, list[str]]) -> dict[str, list[list[str]]]:
    """`by_field`: this kind's rows from `_winners`."""
    preferred = [["Rank (1 wins)", "Dataset", "Rules path"]]
    for i, code in enumerate((rules.get("defaults") or {}).get("sources") or []):
        preferred.append([str(i + 1), _text(code), f"merge/kinds/{kind}.yaml defaults.sources[{i}]"])
    per_field = [["MDM field", "Filled by, first wins", "Winner", "Rule", "Rules path"]]
    for field, (_, row) in by_field.items():
        per_field.append([field, *row])
    classification = [["Rule", "Version", "Dataset", "Step", "Verdict", "Probably", "When", "Rules path"]]
    matching = [["Order", "Rule", "Version", "Links", "To", "Every one of these must hold", "If nothing matches",
                 "Rules path"]]
    order = 0
    for i, rule in enumerate(rules.get("rules") or []):
        at = f"merge/kinds/{kind}.yaml rules[{i}]"
        if rule.get("family") == "classification":
            for j, step in enumerate(rule.get("steps") or []):
                when = "Otherwise" if step.get("otherwise") else _conditions(step.get("when") or [])
                classification.append([_text(rule.get("rule_id")), _text(rule.get("version")),
                                       _text(rule.get("source")), _text(step.get("step")),
                                       _text(step.get("verdict")), _text(step.get("probable_kind")), when,
                                       f"{at}.steps[{j}]"])
        else:
            order += 1
            matching.append([str(order), _text(rule.get("rule_id")), _text(rule.get("version")),
                             _text(rule.get("source")), _text(rule.get("holder_source")),
                             _conditions(rule.get("when") or []), _text(rule.get("on_no_match")), at])
    about = [["What", "Value"], ["How to change this", HOW_TO_CHANGE], ["Kind", kind],
             ["Rules version", _text(rules.get("version"))], ["Proof bar", _text(rules.get("bars"))]]
    return {"Kind": about, "Preferred sources": preferred, "Who wins each field": per_field,
            "Classification": classification, "Matching rules": matching}


# --- which workbooks there are ------------------------------------------------------

def comment_notes(*paths: Path) -> list[list[str]]:
    """The decisions written as comments in rules files, one note per comment
    block, naming the key it sits above. A new workbook starts its Notes
    sheet with them: a rules export drops comments, a workbook keeps them."""
    notes = []
    for path in paths:
        if not path.exists():
            continue
        block: list[str] = []
        for line in path.read_text(encoding="utf-8").splitlines():
            text = line.strip()
            if text.startswith("#"):
                block.append(text.lstrip("#").strip())
            elif block and text:
                about = text.split(":", 1)[0].lstrip("- ").strip()
                notes.append([" ".join(b for b in block if b), f"{path.name}: {about}",
                              "rules file comment", ""])
                block = []
    return notes


def documents(root: Path | None = None) -> dict[Path, tuple[str, dict[str, list[list[str]]], list[Path]]]:
    """Every Mapping Document the rules under `root` generate, by path: the
    source or kind it describes, its sheets, and the rules files behind it."""
    root = root or files.ROOT
    policy = files.policy(root)
    winners = _winners(policy, root)
    found: dict[Path, tuple] = {}
    for path in sorted((root / "sources").glob("*/source.yaml")):
        body = files.load_source(path)
        if body.get("mdm"):  # a source that feeds no MDM kind maps nothing
            name = path.parent.name
            found[path.parent / "MAPPING.xlsx"] = (
                name, _source_sheets(name, body, policy, root), [path, path.parent / "quality.yaml"])
    for kind, rules in sorted((policy.get("kinds") or {}).items()):
        yaml = root / "merge" / "kinds" / f"{kind}.yaml"
        found[yaml.with_suffix(".xlsx")] = (kind, _kind_sheets(kind, rules, winners.get(kind, {})), [yaml])
    return found


# --- the workbook file ----------------------------------------------------------------

def _trim(row: list[str]) -> list[str]:
    """A row without its trailing empty cells, as a spreadsheet reads back."""
    return row[:max((i + 1 for i, v in enumerate(row) if v), default=0)]


def read(path: Path) -> dict[str, list[list[str]]]:
    """A workbook's sheets as rows of text, blank rows kept so a row's number
    is its row in the spreadsheet (trailing blank rows dropped)."""
    from openpyxl import load_workbook

    book = load_workbook(path, read_only=True, data_only=True)
    try:
        sheets = {}
        for sheet in book.worksheets:
            rows = [_trim(["" if v is None else str(v) for v in row]) for row in sheet.iter_rows(values_only=True)]
            while rows and not rows[-1]:
                rows.pop()
            sheets[sheet.title] = rows
        return sheets
    finally:
        book.close()


def write(path: Path, sheets: dict[str, list[list[str]]], sources: list[Path] = ()) -> None:
    """Write a workbook, keeping the Notes sheet an existing one has; a new
    one starts its notes from the comments in its rules files."""
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font

    notes = read(path).get(NOTES) if path.exists() else [NOTES_HEADER, *comment_notes(*sources)]
    book = Workbook()
    book.remove(book.active)
    book.properties.created = book.properties.modified = SAVED_AT
    for title, rows in {**sheets, NOTES: notes or [NOTES_HEADER]}.items():
        sheet = book.create_sheet(title)
        for row in rows:
            sheet.append(row)
        for column in sheet.columns:
            width = max(len(str(c.value or "")) for c in column)
            sheet.column_dimensions[column[0].column_letter].width = min(max(width, 10), 60) + 2
            for c in column:
                c.alignment = Alignment(wrap_text=True, vertical="top")
                if isinstance(c.value, str) and c.value.startswith("="):
                    c.data_type = "s"  # text, never a formula
        for cell in sheet[1]:
            cell.font = Font(bold=True)
        sheet.freeze_panes = "A2"
    # An .xlsx is a zip whose entries carry the time they were written: re-zip
    # them with a fixed one, so unchanged rules write the same bytes.
    buffer = io.BytesIO()
    book.save(buffer)
    fixed = io.BytesIO()
    with zipfile.ZipFile(buffer) as source, zipfile.ZipFile(fixed, "w", zipfile.ZIP_DEFLATED) as target:
        for item in source.infolist():
            entry = zipfile.ZipInfo(item.filename, date_time=SAVED_AT.timetuple()[:6])
            entry.compress_type = zipfile.ZIP_DEFLATED
            data = source.read(item.filename)
            if item.filename == "docProps/core.xml":  # openpyxl stamps the save time here
                data = re.sub(rb"(<dcterms:modified[^>]*>)[^<]*", rb"\g<1>" + _STAMP, data)
            target.writestr(entry, data)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(fixed.getvalue())


def differences(path: Path, sheets: dict[str, list[list[str]]]) -> list[str]:
    """What a workbook says that its rules do not, in plain text: rows added
    or removed, and cells changed. Rows are aligned by content, so one row
    added does not mark every row below it. Notes never differ."""
    if not path.exists():
        return ["missing; run `edgar-warehouse rules mapdoc write`"]
    found = read(path)
    out = []
    for title in sorted((set(sheets) | set(found)) - {NOTES}):
        want, have = sheets.get(title), found.get(title)
        want = None if want is None else [_trim(row) for row in want]
        if want is None or have is None:
            out.append(f"{title}: sheet {'added' if want is None else 'removed'} in the workbook")
            continue
        header = want[0] if want else []
        matcher = difflib.SequenceMatcher(a=[tuple(r) for r in want], b=[tuple(r) for r in have], autojunk=False)
        for op, a0, a1, b0, b1 in matcher.get_opcodes():
            if op == "equal":
                continue
            if op == "replace" and a1 - a0 == b1 - b0:
                for a, b, n in zip(want[a0:a1], have[b0:b1], range(b0, b1)):
                    for j in range(max(len(a), len(b))):
                        x, y = (a[j] if j < len(a) else ""), (b[j] if j < len(b) else "")
                        if x != y:
                            column = header[j] if j < len(header) else f"column {j + 1}"
                            out.append(f"{title} row {n + 1} ({a[0] if a else ''}), {column}: "
                                       f"rules say {json.dumps(x)}, workbook says {json.dumps(y)}")
                continue
            for row in want[a0:a1]:
                out.append(f"{title}: removed in the workbook: {' | '.join(row)}")
            for n, row in zip(range(b0, b1), have[b0:b1]):
                out.append(f"{title} row {n + 1}: added in the workbook: {' | '.join(row)}")
    return out
