"""A GLEIF reporting exception read by its contract alone (L6): the checks the
older reader (`gleif_source.record_evidence`) made, then retained as evidence.
Each case's outcome was compared with that reader on 2026-10-10: all equal."""

import pytest

from edgar_warehouse.mdm.clean.adapters import UnsupportedRecord, normalize
from edgar_warehouse.mdm.clean.gleif_source import dataset_contract

LEI = "HWUPKR0MPOU8FGXBT394"
PUBLICATION = {"publication_key": "p", "revision": 1, "artifact_sha256": "a" * 64,
               "member": "reporting_exceptions", "effective_at": None}


def record(category="DIRECT_ACCOUNTING_CONSOLIDATION_PARENT", reasons=({"$": "NON_CONSOLIDATING"},), lei=LEI,
           deletion=None):
    found = {"LEI": {"$": lei}, "ExceptionCategory": {"$": category}}
    if reasons is not None:
        found["ExceptionReason"] = list(reasons) if isinstance(reasons, tuple) else reasons
    if deletion is not None:
        found["Extension"] = {"gleif:Deletion": deletion}
    return found


@pytest.mark.parametrize("row,reason", [
    (record(), "reported_parent_exception"),
    (record(reasons={"$": "NO_LEI"}), "reported_parent_exception"),
    (record("ULTIMATE_ACCOUNTING_CONSOLIDATION_PARENT"), "reported_parent_exception"),
    (record("SOMETHING"), "unsupported_exception_category"),
    (record(reasons=None), "missing_exception_reason"),
    (record(reasons=()), "missing_exception_reason"),
    (record(reasons={}), "missing_exception_reason"),
    (record(reasons=""), "missing_exception_reason"),
    (record(reasons=({"$": "WHATEVER"},)), "invalid_exception_reason"),
    (record(reasons=({"$": "NO_LEI"}, {"$": "X"})), "invalid_exception_reason"),
    (record(reasons=({"$": 7},)), "invalid_exception_reason"),
    (record(deletion={"$": "x"}), "gleif_deletion_flag"),
    (record(lei="BAD"), "invalid_lei"),
], ids=["valid", "one reason object", "ultimate parent", "other category", "no reason", "empty list",
        "empty object", "empty text", "unknown reason", "one unknown of two", "non-text reason", "deletion flag",
        "bad LEI"])
def test_every_exception_waits_with_the_older_readers_reason(row, reason):
    with pytest.raises(UnsupportedRecord) as refused:
        normalize(row, source_code="gleif.reporting_exceptions.v1", contract=dataset_contract("reporting_exceptions"),
                  publication=PUBLICATION)
    assert refused.value.reason == reason
