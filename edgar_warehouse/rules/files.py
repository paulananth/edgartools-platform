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
from pathlib import Path
from typing import Any

import yaml

# The rules folder: `EDGAR_RULES_ROOT` when set; else this repository's
# `rules/`; else, in an installed data skill bundle with no checkout around
# it, the rules the bundle was built with (mastering to-do 21).
_CHECKOUT = Path(__file__).resolve().parents[2] / "rules"
_BUNDLED = Path(__file__).resolve().parents[1] / "bundle_data" / "rules"
ROOT = Path(os.environ.get("EDGAR_RULES_ROOT") or (_CHECKOUT if _CHECKOUT.is_dir() or not _BUNDLED.is_dir() else _BUNDLED))

_JSON_INT = re.compile(r"-?(?:0|[1-9][0-9]*)")
_JSON_FLOAT = re.compile(r"-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?(?:[eE][-+]?[0-9]+)?")
_LITERALS = {"null": None, "true": True, "false": False}
_STR = "tag:yaml.org,2002:str"
_RESOLVER = yaml.resolver.Resolver()


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


def loads(text: str, name: str = "<rules>") -> Any:
    """The JSON value one rules document holds."""
    try:
        for event in yaml.parse(text, Loader=yaml.SafeLoader):
            if isinstance(event, yaml.AliasEvent) or getattr(event, "anchor", None):
                raise RulesFileError(f"{_where(name, event)}: anchors and aliases are not allowed")
            if getattr(event, "tag", None) is not None:
                raise RulesFileError(f"{_where(name, event)}: tags are not allowed")
        node = yaml.compose(text, Loader=yaml.SafeLoader)
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


def policy(root: Path | None = None) -> dict:
    """The Mastering Policy: `merge/policy.yaml`, one file per kind, and every
    reference table, so the policy's digest also covers the tables its rules
    read (an edit to `reference/sec-place-codes.yaml` is a new policy)."""
    root = root or ROOT
    body = load(root / "merge" / "policy.yaml")
    body["kinds"] = {path.stem: load(path) for path in sorted((root / "merge" / "kinds").glob("*.yaml"))}
    body["reference"] = {path.stem: load(path) for path in sorted((root / "reference").glob("*.yaml"))}
    return body


def write_policy(body: dict, root: Path) -> None:
    """Export the one stored policy into the existing authoring layout: the
    reverse of `policy()`, so kinds and reference tables go back to their own
    files."""
    split = {"kinds": root / "merge" / "kinds", "reference": root / "reference"}
    for key, folder in split.items():
        parts = body.get(key, {})
        if not isinstance(parts, dict) or any(not isinstance(name, str) or not re.fullmatch(r"[a-z][a-z0-9_.-]*", name) for name in parts):
            raise RulesFileError(f"Policy {key} must be path-safe identifiers")
        if {p.stem for p in folder.glob("*.yaml")} - set(parts):
            raise RulesFileError(f"Output folder has {key} absent from this version; use an empty export folder")
    (root / "merge").mkdir(parents=True, exist_ok=True)
    (root / "merge" / "policy.yaml").write_text(dumps({k: v for k, v in body.items() if k not in split}), encoding="utf-8")
    for key, folder in split.items():
        folder.mkdir(parents=True, exist_ok=True)
        for name, value in body.get(key, {}).items():
            (folder / f"{name}.yaml").write_text(dumps(value), encoding="utf-8")


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
