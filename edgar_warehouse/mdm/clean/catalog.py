"""Configured mastering vocabulary; no source or entity choices in the engine."""
from pathlib import Path
import math

from edgar_warehouse.rules import files

RELATIVE = Path("mastering/engine-v1.yaml")


def _selected_path(root=None):
    """An explicit catalog wins; partial authoring roots use the shipped build."""
    if root is not None: return Path(root) / RELATIVE
    selected = files.ROOT / RELATIVE
    if selected.is_file(): return selected
    shipped = files.BUNDLED if files.BUNDLED.is_dir() else Path(files.__file__).resolve().parents[2] / "rules"
    return shipped / RELATIVE


def load(root=None):
    return _validate(files.load(_selected_path(root)))


def _validate(body):
    expected = {"version", "kinds", "profiles", "accepted_bars",
                "reference_tables", "legacy_jurisdiction_table", "pair_comparisons", "legacy_pair_comparison"}
    if (not isinstance(body, dict) or not expected <= set(body)
        or set(body) - expected - {"master_search", "detail_lookups"}
        or not isinstance(body["version"], str) or not body["version"]):
        raise ValueError("Mastering engine catalog must name its version and configured sections")
    if "master_search" in body:
        search = body["master_search"]
        if (not isinstance(search, dict) or set(search) != {"version", "name_fields", "position_weight"}
            or not isinstance(search["version"], str) or not search["version"].strip()
            or not isinstance(search["name_fields"], list) or not search["name_fields"]
            or any(not isinstance(field, str) or not field or field.strip() != field
                   for field in search["name_fields"])
            or len(set(search["name_fields"])) != len(search["name_fields"])
            or type(search["position_weight"]) not in (int, float)
            or not math.isfinite(search["position_weight"]) or not 0 < search["position_weight"] <= 1):
            raise ValueError("Master search needs versioned name fields and a position weight")
    kinds = body["kinds"]
    if "detail_lookups" in body:
        lookup = body["detail_lookups"]
        if (not isinstance(lookup, dict) or set(lookup) != {"version", "kind", "detail", "keys"}
            or any(not isinstance(lookup[part], str) or not lookup[part].strip()
                   or lookup[part].strip() != lookup[part] for part in ("version", "kind", "detail"))
            or not isinstance(kinds, list) or lookup["kind"] not in kinds
            or not isinstance(lookup["keys"], dict) or not lookup["keys"]
            or any(not isinstance(name, str) or not name or name.strip() != name
                   or not isinstance(fields, list) or not fields
                   or any(not isinstance(field, str) or not field or field.strip() != field for field in fields)
                   or len(set(fields)) != len(fields)
                   for name, fields in lookup["keys"].items())):
            raise ValueError("Detail lookups need a version, a configured kind, a detail list and named keys")
    if (not isinstance(kinds, list) or not kinds or not all(isinstance(k, str) and k.strip() == k and k for k in kinds)
        or len(set(kinds)) != len(kinds)):
        raise ValueError("Mastering engine catalog names distinct kinds")
    profiles = body["profiles"]
    if (not isinstance(profiles, dict) or any(not isinstance(role, str) or not role or not isinstance(allowed, list)
        or not allowed or not all(isinstance(k, str) for k in allowed) or set(allowed) - set(kinds)
        or len(set(allowed)) != len(allowed) for role, allowed in profiles.items())):
        raise ValueError("Mastering profile eligibility names configured kinds")
    bars = body["accepted_bars"]
    if not isinstance(bars, dict) or set(bars) - set(kinds):
        raise ValueError("Mastering accepted bars name configured kinds")
    for families in bars.values():
        if not isinstance(families, dict): raise ValueError("Mastering accepted bars name decision families")
        for family, bar in families.items():
            if (not isinstance(family, str) or not family or not isinstance(bar, dict)
                or set(bar) != {"min_precision", "one_sided_confidence"}
                or any(type(v) not in (int, float) or not math.isfinite(v) or not 0 < v < 1 for v in bar.values())
                or bar["one_sided_confidence"] <= 0.5):
                raise ValueError("Mastering accepted bar is invalid")
    references = body["reference_tables"]
    if (not isinstance(references, dict) or not references
        or any(not isinstance(alias, str) or not alias or not isinstance(spec, dict)
               or set(spec) != {"pin", "target_set", "match_type"}
               or any(not isinstance(value, str) or not value or value.strip() != value for value in spec.values())
               for alias, spec in references.items())
        or not isinstance(body["legacy_jurisdiction_table"], str)
        or body["legacy_jurisdiction_table"] not in references):
        raise ValueError("Mastering reference tables name pinned crosswalk selectors and a configured compatibility table")
    comparisons = body["pair_comparisons"]
    if (not isinstance(comparisons, dict) or not comparisons
        or any(not isinstance(alias, str) or not alias or alias.strip() != alias for alias in comparisons)
        or not isinstance(body["legacy_pair_comparison"], str)
        or body["legacy_pair_comparison"] not in comparisons):
        raise ValueError("Mastering pair comparison names configured selectors and a compatibility profile")
    for pair in comparisons.values():
        _validate_pair_comparison(pair, kinds)
    return body


def _validate_pair_comparison(pair, kinds):
    text_fields = {"name_field", "identifier_namespace", "census_field", "census_entries_field",
                   "census_holder_keys_field", "census_holder_count_field", "census_identifier_count_field",
                   "census_other_holders_field", "cascade_field", "cascade_identifier_field",
                   "eligibility_kind", "status_field", "registration_status_field"}
    list_fields = {"eligibility_categories", "left_address_fields", "right_address_fields"}
    if (not isinstance(pair, dict) or set(pair) != text_fields | list_fields
        or any(not isinstance(pair[key], str) or not pair[key] or pair[key].strip() != pair[key]
               for key in text_fields)
        or pair["eligibility_kind"] not in kinds
        or any(not isinstance(pair[key], list) or not pair[key]
               or any(not isinstance(value, str) or not value or value.strip() != value for value in pair[key])
               or len(set(pair[key])) != len(pair[key]) for key in list_fields)):
        raise ValueError("Mastering pair comparison requires configured record selectors and eligibility")


LOADED_PATH = _selected_path().resolve()
LOADED_BYTES = LOADED_PATH.read_bytes()
CATALOG = _validate(files.loads(LOADED_BYTES.decode("utf-8"), LOADED_PATH.name))


def assert_current():
    """A running process cannot adopt a different catalog under an old snapshot."""
    if _selected_path().resolve() != LOADED_PATH or LOADED_PATH.read_bytes() != LOADED_BYTES:
        raise ValueError("Mastering engine catalog changed after loading; start a new qualified execution")


def path(root=None):
    if root is not None: return _selected_path(root)
    assert_current()
    return LOADED_PATH
