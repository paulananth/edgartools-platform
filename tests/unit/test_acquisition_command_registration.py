"""Retired acquisition commands cannot resolve through the old runtime registry."""
from datetime import UTC, datetime

import pytest

from edgar_warehouse.application.acquisition_command_registry import (
    AcquisitionCommandRegistration,
    acquisition_command_registration,
    build_acquisition_command_registry,
    registered_acquisition_handlers,
)


def test_old_acquisition_commands_are_unregistered():
    retired = (
        "load-daily-form-index-for-date", "capture-filing-artifact",
        "drive-filing-discovery-for-date", "drive-submissions-discovery",
        "drive-company-facts-discovery", "drive-reference-catalog-discovery",
        "drive-adv-bulk-dataset-discovery", "drive-adv-filing-discovery-for-date",
    )
    assert not registered_acquisition_handlers()
    for name in retired:
        assert acquisition_command_registration(name) is None


def test_registration_still_rejects_missing_behavior_and_duplicate_name():
    with pytest.raises(TypeError, match="execute must be callable"):
        AcquisitionCommandRegistration("bad", None, lambda **_: {}, lambda **_: {})
    valid = AcquisitionCommandRegistration("duplicate", lambda _: 0,
                                           lambda **_: {}, lambda **_: {})
    with pytest.raises(ValueError, match="Duplicate acquisition command registration"):
        build_acquisition_command_registry((valid, valid))
