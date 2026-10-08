"""Rules files: the YAML a person edits, read and written exactly.

A rules file holds JSON values only, so what a reader sees is what a digest
covers. Plain YAML guesses types (`yes`, `010`, `2026-09-25`, an empty value),
and a guess would change a digest without anyone seeing it. So the loader:
- reads an unquoted `null`, `true`, `false` or JSON number as that value;
- refuses any other unquoted value YAML would read as a non-string, and says
  to quote it;
- reads every other unquoted value, and every key, as text;
- refuses duplicate keys, anchors, aliases, tags and more than one document.

The writer quotes any string the loader would not read back as that string.
"""

from __future__ import annotations

import os
import re
import shutil
from pathlib import Path
from typing import Any

import yaml

# The rules folder: `EDGAR_RULES_ROOT` when set. Else, in an installed data
# skill bundle (mastering to-do 21), the rules it was built with, read only:
# `BUNDLED` exists only beside an installed copy of this file. Else this
# repository's `rules/`.
BUNDLE_DATA = Path(__file__).resolve().parents[1] / "bundle_data"
BUNDLED = BUNDLE_DATA / "rules"
ROOT = Path(os.environ.get("EDGAR_RULES_ROOT")
            or (BUNDLED if BUNDLED.is_dir() else Path(__file__).resolve().parents[2] / "rules"))


def writable(root: Path) -> Path:
    """`root`, unless it is the bundled copy, which a reinstall replaces."""
    if Path(root).resolve().is_relative_to(BUNDLE_DATA):
        raise ValueError("The bundled rules are read only: copy them with "
                         "`edgar-warehouse skill install --rules <folder>` and set EDGAR_RULES_ROOT")
    return Path(root)


_JSON_INT = re.compile(r"-?(?:0|[1-9][0-9]*)")
_JSON_FLOAT = re.compile(r"-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?(?:[eE][-+]?[0-9]+)?")
_LITERALS = {"null": None, "true": True, "false": False}
_STR = "tag:yaml.org,2002:str"
_RESOLVER = yaml.resolver.Resolver()
# Keep the same node/event validation with the compiled parser when available.
_RULES_LOADER = getattr(yaml, "CSafeLoader", yaml.SafeLoader)


class RulesFileError(ValueError):
    """A rules file that does not hold exactly one JSON document."""


def _where(name: str, node_or_event) -> str:
    return f"{name}:{node_or_event.start_mark.line + 1}"


def _plain(value: str) -> tuple[bool, Any]:
    """How the loader reads an unquoted value: (allowed, value)."""
    if value in _LITERALS:
        return True, _LITERALS[value]
    if _JSON_INT.fullmatch(value):
        return True, int(value)
    if _JSON_FLOAT.fullmatch(value):
        return True, float(value)
    if _RESOLVER.resolve(yaml.ScalarNode, value, (True, False)) != _STR:
        return False, None
    return True, value


def _reads_as_text(value: str) -> bool:
    allowed, read = _plain(value)
    return allowed and read == value and type(read) is str


def _value(node, name: str) -> Any:
    if isinstance(node, yaml.ScalarNode):
        if node.style:
            return node.value
        allowed, read = _plain(node.value)
        if not allowed:
            shown = repr(node.value) if node.value else "an empty value"
            raise RulesFileError(
                f"{_where(name, node)}: {shown} is ambiguous; quote it as "
                "text, or write null, true, false or a JSON number"
            )
        return read
    if isinstance(node, yaml.SequenceNode):
        return [_value(item, name) for item in node.value]
    result: dict[str, Any] = {}
    for key, item in node.value:
        if not isinstance(key, yaml.ScalarNode):
            raise RulesFileError(f"{_where(name, key)}: a key must be text")
        if key.value in result:
            raise RulesFileError(f"{_where(name, key)}: duplicate key {key.value!r}")
        result[key.value] = _value(item, name)
    return result


def _rules_node(text: str, name: str, loader):
    for event in yaml.parse(text, Loader=loader):
        if isinstance(event, yaml.AliasEvent) or getattr(event, "anchor", None):
            raise RulesFileError(f"{_where(name, event)}: anchors and aliases are not allowed")
        if getattr(event, "tag", None) is not None:
            raise RulesFileError(f"{_where(name, event)}: tags are not allowed")
    return yaml.compose(text, Loader=loader)


def loads(text: str, name: str = "<rules>") -> Any:
    """The JSON value one rules document holds."""
    try:
        # libyaml accepts tabs in some unquoted positions the existing Python
        # scanner refuses. Use that scanner for all tab-containing documents
        # so quoted/block tabs and plain-scalar refusals retain their semantics.
        loader = yaml.SafeLoader if "\t" in text else _RULES_LOADER
        try:
            node = _rules_node(text, name, loader)
        except yaml.YAMLError:
            if loader is yaml.SafeLoader:
                raise
            # libyaml is stricter about escaped surrogate code points. Preserve
            # the existing reader's acceptance; downstream UTF-8/digest checks
            # remain authoritative. Both paths apply the same event/node rules.
            node = _rules_node(text, name, yaml.SafeLoader)
    except yaml.YAMLError as error:
        raise RulesFileError(f"{name}: {error}") from error
    if node is None:
        raise RulesFileError(f"{name}: the file is empty")
    return _value(node, name)


def load(path: Path) -> Any:
    return loads(path.read_text(encoding="utf-8"), str(path))


class _Dumper(yaml.SafeDumper):
    def ignore_aliases(self, data: Any) -> bool:
        return True


def _represent_str(dumper: yaml.SafeDumper, value: str):
    return dumper.represent_scalar(_STR, value, style=None if _reads_as_text(value) else '"')


_Dumper.add_representer(str, _represent_str)


def dumps(value: Any) -> str:
    """YAML the loader reads back as exactly `value`."""
    return yaml.dump(value, Dumper=_Dumper, sort_keys=False, allow_unicode=True, width=88)


def source(name: str, root: Path | None = None) -> dict:
    """One source's document: `rules/sources/<name>/source.yaml`, with its
    `quality.yaml` beside it when there is one."""
    return load_source((root or ROOT) / "sources" / name / "source.yaml")


def load_source(path: Path) -> dict:
    """A source's Rules document. The feed's quality rule (company mastering
    ticket 22) is its own file and version label, and rides in each Dataset
    Contract it names as `quality`, so one approval and one digest cover the
    mapping and the checks that run with it, as `policy()` does for kinds."""
    body = load(path)
    quality_path = path.parent / "quality.yaml"
    if not quality_path.exists():
        return body
    quality = load(quality_path)
    if not isinstance(quality, dict) or set(quality) != {"version", "quality"} or not isinstance(quality["quality"], dict):
        raise RulesFileError(f"{quality_path}: holds version and quality only")
    for code, block in quality["quality"].items():
        if not isinstance(block, dict):
            raise RulesFileError(f"{quality_path}: {code} holds fixes and checks")
        contract = ((body.get("mdm") or {}).get(code) or {}).get("contract")
        if not isinstance(contract, dict):
            raise RulesFileError(f"{quality_path}: {code} is not a Dataset Contract in source.yaml")
        if "quality" in contract:
            raise RulesFileError(f"{path}: write quality in quality.yaml, not in the contract")
        contract["quality"] = {"version": quality["version"], **block}
    return body


def write_source(body: dict, folder: Path) -> None:
    """The reverse of `load_source`: the quality blocks go back to quality.yaml."""
    import copy

    body = copy.deepcopy(body)
    blocks, versions = {}, set()
    for code, entry in (body.get("mdm") or {}).items():
        block = (entry.get("contract") or {}).pop("quality", None)
        if block is not None:
            versions.add(block.pop("version", None))
            blocks[code] = block
    # Refuse before writing anything, so a refused export leaves no half.
    if blocks and (len(versions) != 1 or not isinstance(next(iter(versions)), str)):
        raise RulesFileError("One source's contracts carry one named quality version")
    quality_path = folder / "quality.yaml"
    if not blocks and quality_path.exists():
        raise RulesFileError(f"{quality_path} is absent from this version; use an empty export folder")
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "source.yaml").write_text(dumps(body), encoding="utf-8")
    if blocks:
        quality_path.write_text(dumps({"version": versions.pop(), "quality": blocks}), encoding="utf-8")


def pipeline(name: str, root: Path | None = None) -> dict:
    """A platform job uses the same Rules lifecycle as a source document."""
    return load((root or ROOT) / "pipelines" / name / "pipeline.yaml")


def mdm_contract(source_name: str, source_code: str, root: Path | None = None) -> dict:
    """The Dataset Contract one source registers under `source_code`."""
    return source(source_name, root)["mdm"][source_code]["contract"]


# The policy's sections kept in one file each under `merge/`, loaded when the
# file exists and written back by `write_policy` (GoF consult, profiling ticket
# 02: the relationship types, then the reference pins, each grew this by hand).
POLICY_FILES = {
    # The relationship types MDM masters (profiling ticket 04): data, not code.
    "relationships": "relationships.yaml",
    # The reference data the rules read, pinned by RDM version and sha256
    # (profiling ticket 02).
    "reference_pins": "reference-pins.yaml",
}


def policy(root: Path | None = None) -> dict:
    """The Mastering Policy: `merge/policy.yaml`, one file per kind, and the
    sections in POLICY_FILES: the relationship types and the pins of the
    reference data its rules read (each an RDM code set version and its
    sha256), so the policy's digest covers that data (a new version is a new
    pin, so a new policy). Until profiling ticket 02 the tables themselves were
    embedded, as `reference`."""
    root = root or ROOT
    body = load(root / "merge" / "policy.yaml")
    body["kinds"] = {path.stem: load(path) for path in sorted((root / "merge" / "kinds").glob("*.yaml"))}
    for key, name in POLICY_FILES.items():
        if (root / "merge" / name).exists():
            body[key] = load(root / "merge" / name)
    return body


def write_policy(body: dict, root: Path) -> None:
    """Export the one stored policy into the existing authoring layout: the
    reverse of `policy()`, so kinds and each POLICY_FILES section go back to
    their own files. A policy stored before profiling ticket 02 embedded its
    reference tables (`reference`); those go back to `reference/<name>.yaml`,
    and only such a body checks that folder (today it also holds tables the
    policy no longer embeds)."""
    split = {"kinds": root / "merge" / "kinds"}
    if "reference" in body:
        split["reference"] = root / "reference"
    for key, folder in split.items():
        parts = body.get(key, {})
        if not isinstance(parts, dict) or any(not isinstance(name, str) or not re.fullmatch(r"[a-z][a-z0-9_.-]*", name) for name in parts):
            raise RulesFileError(f"Policy {key} must be path-safe identifiers")
        if {p.stem for p in folder.glob("*.yaml")} - set(parts):
            raise RulesFileError(f"Output folder has {key} absent from this version; use an empty export folder")
    (root / "merge").mkdir(parents=True, exist_ok=True)
    (root / "merge" / "policy.yaml").write_text(
        dumps({k: v for k, v in body.items() if k not in split and k not in POLICY_FILES}), encoding="utf-8")
    for key, name in POLICY_FILES.items():
        path = root / "merge" / name
        if key in body:
            path.write_text(dumps(body[key]), encoding="utf-8")
        elif path.exists():
            raise RulesFileError(f"Output folder has {key} absent from this version; use an empty export folder")
    for key, folder in split.items():
        folder.mkdir(parents=True, exist_ok=True)
        for name, value in body.get(key, {}).items():
            (folder / f"{name}.yaml").write_text(dumps(value), encoding="utf-8")
    # The pinned versions' published files, so the export reads on its own.
    for pin in (body.get("reference_pins") or {}).values():
        relative = Path("reference") / "published" / pin["code_set"] / str(pin["version"])
        if (root / relative).resolve() == (ROOT / relative).resolve():
            continue
        if not (ROOT / relative / "canonical.jsonl").exists():
            raise RulesFileError(f"The pinned reference data {pin['code_set']} {pin['version']} is not published here")
        (root / relative).mkdir(parents=True, exist_ok=True)
        for name in ("canonical.jsonl", "pin.json"):
            if (ROOT / relative / name).exists():
                shutil.copyfile(ROOT / relative / name, root / relative / name)


def pending_proofs(root: Path | None = None) -> dict:
    """Proofs of declared rules that wait for the operator's approval."""
    return load((root or ROOT) / "merge" / "pending-proofs.yaml")


def approve_rule(rule_id: str, *, by: str, words: str, at: str, root: Path | None = None) -> dict:
    """Switch one declared merge rule on, on the operator's words: its proof in
    `pending-proofs.yaml` goes into `policy.yaml` with the approval stamped on
    it. Appended as text, so the policy's comments stay. No proof, no approval;
    a proof that falls short of its kind's bar is refused with the reason."""
    from edgar_warehouse.mdm.clean.activation import check_policy

    root = root or ROOT
    if not by.strip() or not words.strip():
        raise RulesFileError("An approval names who approved and holds their exact words")
    proof = pending_proofs(root).get(rule_id)
    if not isinstance(proof, dict):
        raise RulesFileError(f"No test evidence for rule {rule_id}: it has no proof in merge/pending-proofs.yaml")
    body = policy(root)
    declared = [(kind, rule) for kind, rules in body["kinds"].items()
                for rule in rules.get("rules") or [] if rule.get("rule_id") == rule_id]
    if len(declared) != 1:
        raise RulesFileError(f"Rule {rule_id} is declared {len(declared)} times in merge/kinds")
    if any(entry.get("rule_id") == rule_id for entry in body.get("automatic_rules") or []):
        raise RulesFileError(f"Rule {rule_id} is already switched on")
    kind, rule = declared[0]
    entry = {"kind": kind, "family": rule["family"], "rule_id": rule_id, "rule_version": rule["version"],
             "verdict": rule["emits"][0], "activation": "measured",
             "proof": {**proof, "approved_by": by, "approved_at": at, "approved_words": words}}
    check_policy({**body, "automatic_rules": [*(body.get("automatic_rules") or []), entry]})
    path = root / "merge" / "policy.yaml"
    text = path.read_text(encoding="utf-8")
    note = f"# {rule_id}: switched on by {by}, {at}, in their words: {words}".replace("\n", " ")
    path.write_text(text.rstrip("\n") + "\n" + note + "\n" + dumps([entry]), encoding="utf-8")
    if (load(path).get("automatic_rules") or [])[-1] != entry:
        path.write_text(text, encoding="utf-8")
        raise RulesFileError("policy.yaml did not take the entry as written; left unchanged")
    return entry


def reference(name: str, root: Path | None = None) -> dict:
    """A reference table rules and readers share: `reference/<name>.yaml`."""
    return load((root or ROOT) / "reference" / f"{name}.yaml")


def reference_pin(name: str, root: Path | None = None) -> dict:
    """The Mastering Policy's pin of the reference data named `name`:
    `{code_set, version, sha256}` from `merge/reference-pins.yaml`."""
    root = root or ROOT
    pins = root / "merge" / "reference-pins.yaml"
    if not pins.exists():
        raise RulesFileError(f"{root} has no merge/reference-pins.yaml: install rules from this build "
                             "(the policy pins its reference data since profiling ticket 02)")
    pin = load(pins).get(name)
    if pin is None:
        raise RulesFileError(f"The Mastering Policy pins no reference data named {name}")
    return pin


def pinned_reference(name: str, root: Path | None = None) -> list[dict]:
    """The codes of the reference data the Mastering Policy pins under `name`:
    its published canonical form, refused unless its sha256 is the pin. Each
    code carries its `labels` and `crosswalk` as lists ([to_set, to_version,
    to_code, match_type]), as RDM publishes them (docs/specs/rdm/spec.md §4)."""
    import hashlib
    import json

    root = root or ROOT
    pin = reference_pin(name, root)
    path = root / "reference" / "published" / pin["code_set"] / str(pin["version"]) / "canonical.jsonl"
    data = path.read_bytes()
    if hashlib.sha256(data).hexdigest() != pin["sha256"]:
        raise RulesFileError(f"Reference data {pin['code_set']} {pin['version']} differs from its pinned sha256")
    return [json.loads(line) for line in data.decode("utf-8").splitlines()]


def _write_plain(body: dict, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(dumps(body), encoding="utf-8")


# How each Rules document kind is read from, and written back to, its
# authoring files, given the path of its main file (`<source>/source.yaml`,
# `<pipeline>/pipeline.yaml`, `merge/policy.yaml`). Every reader and writer
# of documents uses this table, so a kind whose layout splits (merge into
# kinds and reference tables; source into source and quality) changes here
# only.
LAYOUT = {
    "source": (load_source, lambda body, path: write_source(body, path.parent)),
    "pipeline": (load, _write_plain),
    "merge": (lambda path: policy(path.parents[1]), lambda body, path: write_policy(body, path.parents[1])),
}
