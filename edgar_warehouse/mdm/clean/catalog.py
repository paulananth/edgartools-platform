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
    expected = {"version", "kinds", "profiles", "accepted_bars", "legacy_relationships", "legacy_ultimate_type"}
    if not isinstance(body, dict) or set(body) != expected or not isinstance(body["version"], str) or not body["version"]:
        raise ValueError("Mastering engine catalog must name its version and configured sections")
    kinds = body["kinds"]
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
    if not isinstance(body["legacy_relationships"], dict) or not isinstance(body["legacy_ultimate_type"], str) or not body["legacy_ultimate_type"]:
        raise ValueError("Mastering legacy relationship contract is invalid")
    return body


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
