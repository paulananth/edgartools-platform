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


def context_subjects(root: Path | None = None) -> frozenset[str]:
    """Configured context namespace, independent of any store implementation."""
    body = load((root or ROOT) / "context" / "definitions.yaml")
    names = body.get("kinds") if isinstance(body, dict) else None
    if (not isinstance(names, dict) or not all(isinstance(n, str) and n.strip() == n and n for n in names)):
        raise RulesFileError("Context definitions name the configured kinds")
    return frozenset({*names, "relationship"})


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
    from .shape import expand_source
    body = expand_source(load(path))  # targets written in the one shape, as the steps the engine runs
    if isinstance(body, dict) and "mdm" in body:  # the section was named `mdm` until ticket 171
        raise RulesFileError(f"{path}: the `mdm` section is now `dataset_contracts` (ticket 171); rename it")
    quality_path = path.parent / "quality.yaml"
    if not quality_path.exists():
        return body
    quality = load(quality_path)
    if not isinstance(quality, dict) or set(quality) != {"version", "quality"} or not isinstance(quality["quality"], dict):
        raise RulesFileError(f"{quality_path}: holds version and quality only")
    for code, block in quality["quality"].items():
        if not isinstance(block, dict):
            raise RulesFileError(f"{quality_path}: {code} holds fixes and checks")
        contract = ((body.get("dataset_contracts") or {}).get(code) or {}).get("contract")
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
    for code, entry in (body.get("dataset_contracts") or {}).items():
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


def identifiers(root: Path | None = None) -> dict[str, dict]:
    """The declared identifier types: `rules/identifiers/<name>.yaml`, by name."""
    folder = (root or ROOT) / "identifiers"
    return {path.stem: load(path) for path in sorted(folder.glob("*.yaml"))}


def copy_identifiers(root: Path) -> None:
    """Put the declared identifier types beside an export, so it runs on its
    own: they are formats and normalizers of the build, not stored versions."""
    if (Path(root) / "identifiers").resolve() == (ROOT / "identifiers").resolve():
        return
    (Path(root) / "identifiers").mkdir(parents=True, exist_ok=True)
    for path in sorted((ROOT / "identifiers").glob("*.yaml")):
        shutil.copyfile(path, Path(root) / "identifiers" / path.name)


def pipeline(name: str, root: Path | None = None) -> dict:
    """A platform job is a rules document like a source."""
    return load((root or ROOT) / "pipelines" / name / "pipeline.yaml")


def mdm_contract(source_name: str, source_code: str, root: Path | None = None) -> dict:
    """The Dataset Contract one source registers under `source_code`."""
    return source(source_name, root)["dataset_contracts"][source_code]["contract"]


# The policy's sections kept in one file each under `merge/`, loaded when the
# file exists and written back by `write_policy` (GoF consult, profiling ticket
# 02: the relationship types, then the reference pins, each grew this by hand).
POLICY_FILES = {
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
    return published_reference(reference_pin(name, root), root)


def published_reference(pin: dict, root: Path | None = None) -> list[dict]:
    """The codes of one pinned RDM code set version (`{code_set, version,
    sha256}`, as a policy holds it), refused unless its sha256 is the pin."""
    import hashlib
    import json

    root = root or ROOT
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


def entity_types(body: dict) -> dict[str, dict]:
    """Where each Dataset Contract of a source gets its records' entity type (mastering step 1, settled as a record
    arrives): `fixed` (the contract names one kind), `rule` (a classification rule decides) or `source_field` (the
    source's own category field, mapped by `kind_values`). A contract that states none is refused: no record of it
    could be given its one entity type."""
    found = {}
    for code, spec in (body.get("dataset_contracts") or {}).items():
        adapter = (spec.get("contract") or {}).get("adapter") or {}
        if adapter.get("kind"):
            found[code] = {"origin": "fixed", "types": [adapter["kind"]]}
        elif adapter.get("classification"):
            found[code] = {"origin": "rule", "types": [adapter["classification"]["kind"]],
                           "rule_id": adapter["classification"].get("rule_id")}
        elif adapter.get("kind_field") and adapter.get("kind_values"):
            found[code] = {"origin": "source_field", "types": sorted(set(adapter["kind_values"].values())),
                           "field": adapter["kind_field"]}
        else:
            raise RulesFileError(f"Dataset Contract {code} states no entity type: give it `kind`, a `classification` "
                                 "rule or a `kind_field` with `kind_values`")
    return found


def check_document(kind: str, body: dict) -> None:
    """Refuse a rules document that cannot run as it stands: the one list of
    checks a run and `rules check` share. The body holds JSON values only (a
    loaded file always does; a body built in code may not); a source's Bookkeeping
    targets and acquisition hold; the merge rules pass `check_policy`."""
    if loads(dumps(body)) != body:
        raise RulesFileError("The document holds a value that is not JSON (a tuple, a number as a key)")
    if kind == "source":
        from edgar_warehouse.bookkeeping.clean.config import validate

        entity_types(body)

        for target in ((body.get("bookkeeping") or {}).get("targets") or {}):
            validate(body, target)
        if "acquisition" in body:
            from edgar_warehouse.rules.acquisition_authority import acquisition

            acquisition(body)
    elif kind == "merge":
        from edgar_warehouse.mdm.activation import check_policy

        check_policy(body)


def documents(root: Path | None = None) -> list[tuple[str, str, Path]]:
    """Every rules document under the root: (kind, name, path)."""
    root = root or ROOT
    found = [(kind, path.parent.name, path)
             for kind, folder, filename in (("source", "sources", "source.yaml"), ("pipeline", "pipelines", "pipeline.yaml"))
             for path in sorted((root / folder).glob(f"*/{filename}"))]
    if (root / "merge/policy.yaml").exists():
        found.append(("merge", "platform", root / "merge/policy.yaml"))
    return found


def check(names: list[str] | None = None, root: Path | None = None) -> dict:
    """Each rules file loaded and checked as a run checks it, offline: `ok`, or the
    reason it is refused. Named sources only, when names are given. A loader's message
    can quote a private YAML line, so its refusal names the error's kind and the file only."""
    from edgar_warehouse.control_contract import Blocked
    from edgar_warehouse.mdm.store import Conflict

    results = {}
    for kind, name, path in documents(root):
        if names and (kind != "source" or name not in names):
            continue
        try:
            check_document(kind, LAYOUT[kind][0](path))
            results[f"{kind}:{name}"] = "ok"
        except RulesFileError as error:
            results[f"{kind}:{name}"] = f"refused ({type(error).__name__}): {path}"
        except (Blocked, Conflict) as error:  # the engine's own fixed words, never a file's line
            results[f"{kind}:{name}"] = f"refused ({type(error).__name__}): {error}: {path}"
    missing = sorted(set(names or ()) - {key.split(":", 1)[1] for key in results if key.startswith("source:")})
    for name in missing:
        results[f"source:{name}"] = f"refused (missing): no {root or ROOT}/sources/{name}/source.yaml"
    return results
