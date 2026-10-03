"""A real release-sequence gap, drafted for review without activating source rules."""
import json

import pytest

from edgar_warehouse.mdm.clean.gleif_source import release_sequence
from edgar_warehouse.rules.mapdoc import custom_parsing
from edgar_warehouse.rules.source_engine import SourceEngine, SourceRejected
from edgar_warehouse.rules.steps import epoch_microseconds


@pytest.mark.parametrize("value", ["1970-01-01T00:00:00Z", "1969-12-31T23:59:59.999999Z",
                                  "2026-10-03T08:30:00.123456-04:00", "2026-10-03T12:30:00.123456+00:00"])
def test_generic_step_matches_existing_gleif_release_sequence_exactly(value):
    assert epoch_microseconds(value) == release_sequence(value)


@pytest.mark.parametrize("value", [None, True, 0, 1.5, "", "bad", "2026-10-03", "2026-10-03T12:30:00"])
def test_step_refuses_values_without_an_explicit_timestamp(value):
    with pytest.raises((ValueError, TypeError)):
        epoch_microseconds(value)


def test_trial_proves_configuration_gap_then_custom_result_and_mapping():
    timestamp = "2026-10-03T08:30:00.123456-04:00"
    def contract(expression):
        return {"read": {"format": "jsonl", "tables": {"release": {"each": "record", "columns": {
            "sequence": expression}}}}}
    data = json.dumps({"released_at": timestamp}).encode() + b"\n"
    # Date normalizes the instant but returns text; number cannot convert the instant.
    date = {"date": {"path": "released_at"}}
    assert SourceEngine(contract(date)).read(data).tables["release"][0]["sequence"] == "2026-10-03T12:30:00.123456+00:00"
    assert SourceEngine(contract({"number": {"path": "released_at"}})).read(data).tables["release"][0]["sequence"] is None
    expression = {"custom": {"step": "epoch_microseconds@1", "inputs": {"value": date}}}
    trial = contract(expression)
    assert SourceEngine(trial).read(data).tables["release"][0]["sequence"] == release_sequence(timestamp)
    assert custom_parsing(trial["read"])[1][:2] == ["epoch_microseconds@1", "read.tables.release.columns.sequence.custom"]
    with pytest.raises(SourceRejected, match="invalid_value"):
        SourceEngine(trial).read(b'{"released_at":"bad"}\n')
