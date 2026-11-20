"""What a run holds in the database: a target at grain `run` holds no step (the loader does them all); a target held
by the unit holds every step."""
from copy import deepcopy

import pytest

from edgar_warehouse.bookkeeping.clean.config import Blocked, staged, validate
from edgar_warehouse.rules.files import source

REF = {"uri": "file:///captured/a.json", "sha256": "a" * 64}
STEPS = [
    {"name": "read", "operation": "source.read", "requires": [], "checks": ["x"]},
    {"name": "combine", "operation": "source.combine", "requires": ["read"], "checks": ["x"]},
    {"name": "prepare", "operation": "mdm.prepare", "requires": ["combine"], "checks": ["x"]},
    {"name": "merge", "operation": "mastering.merge", "requires": ["prepare"], "checks": ["x"]},
]


def by_the_unit(name: str) -> dict:
    """A source's rules with its targets held by the unit."""
    body = deepcopy(source(name))
    for target in body["bookkeeping"]["targets"].values():
        target.pop("grain", None)
    return body


@pytest.mark.parametrize("setting", [{"lease_seconds": 300}, {"heartbeat_seconds": 30}])
def test_a_target_at_grain_run_refuses_what_only_a_target_held_by_the_unit_reads(setting):
    body = deepcopy(source("openfigi"))
    body["bookkeeping"]["targets"]["mastering"].update(setting)

    with pytest.raises(Blocked, match=f"holds no unit or lease: remove {next(iter(setting))}"):
        validate(body, "mastering")


def test_a_target_naming_local_is_refused():
    body = by_the_unit("sec.nport.registrant")
    body["bookkeeping"]["targets"]["mastering"]["local"] = True

    with pytest.raises(Blocked, match="Unknown target option"):
        validate(body, "mastering")


def test_no_target_at_grain_run_names_a_setting_it_does_not_read():
    from edgar_warehouse.bookkeeping.clean.config import HELD_BY_THE_UNIT
    from edgar_warehouse.rules import files

    named = {f"{path.parent.name}/{name}": sorted(HELD_BY_THE_UNIT & set(target))
             for path in sorted((files.sources_root()).glob("*/source.yaml"))
             for name, target in (source(path.parent.name).get("bookkeeping", {}).get("targets") or {}).items()
             if target.get("grain") == "run"}
    assert {name: found for name, found in named.items() if found} == {}


def test_the_driver_waits_only_for_the_steps_the_database_run_holds():
    from edgar_warehouse.rules.driving import run_steps

    assert run_steps(deepcopy(source("openfigi")), "mastering") == []  # grain run: the loader does every step
    unmarked = by_the_unit("sec.nport.registrant")
    assert [s["name"] for s in run_steps(unmarked, "mastering")] == [
        s["name"] for s in validate(unmarked, "mastering")["steps"]]


def test_a_target_at_grain_run_keeps_no_step_in_the_database_and_its_manifest_is_still_checked():
    """Bookkeeping holds the run's start and completion only: the run has no step and no unit, and the manifest
    is checked against the steps the loader will run."""
    from edgar_warehouse.bookkeeping.clean.config import worklist

    body = deepcopy(source("sec.nport.registrant"))
    config = staged(validate(body, "mastering"))

    assert config["steps"] == [] and config["loader_steps"]
    whole = {"version": 2, "steps": {step["name"]: [] for step in config["loader_steps"]}}
    with pytest.raises(Blocked, match="Zero work"):
        worklist(whole, config)  # checked as the loader will run it
    assert worklist(whole, {**config, "allow_zero_work": True}) == []
    with pytest.raises(Blocked, match="exactly the configured steps"):
        worklist({"version": 2, "steps": {}}, {**config, "allow_zero_work": True})


@pytest.mark.parametrize("change, message", [({"grain": "off"}, "grain is one of"), ({"grain": False}, "grain is one of"),
                                             ({"grain": "bundle"}, "grain is one of")])
def test_a_grain_is_unit_or_run(change, message):
    body = by_the_unit("sec.nport.registrant")
    body["bookkeeping"]["targets"]["mastering"].update(change)

    with pytest.raises(Blocked, match=message):
        validate(body, "mastering")


def test_a_target_that_names_no_grain_is_held_by_the_unit():
    config = validate(by_the_unit("sec.nport.security"), "mastering")
    assert "grain" not in config
    assert staged(config)["steps"] == config["steps"]


@pytest.mark.parametrize("setting", [{"key": "(?P<year>[0-9]{4})"}, {"key": "(?P<year>[0-9]{4})q(?P<quarter>[1-4])", "fact": "unknown"},
                                     {"key": "("}, {"pattern": "x"}, "2026q2"])
def test_a_delivery_date_is_read_by_a_pattern_naming_its_parts_into_a_fact_the_run_declares(setting):
    body = deepcopy(source("sec.ncen.fund"))
    assert validate(body, "mastering")["delivered"]["key"].endswith("_ncen\\.zip$")
    body["bookkeeping"]["targets"]["mastering"]["delivered"] = setting

    with pytest.raises(Blocked, match="`delivered` is"):
        validate(body, "mastering")
