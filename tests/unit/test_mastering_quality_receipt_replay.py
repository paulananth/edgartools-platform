"""A quality replay must retain the committed files already held by the journal."""

import pytest

from edgar_warehouse.workers.mastering_merge import _attach_replayed_quality


def test_replayed_quality_does_not_replace_committed_file_receipt():
    files = [{"file": "committed-file", "records": 4}]
    outcome = {"version": "source-quality-v1", "table": "source.v1", "checks": {}}
    done = {2: {"files": files, "quality": None}}
    replayed = {2: {"files": [], "quality": outcome}}

    combined = _attach_replayed_quality(done, replayed)

    assert combined[2]["files"] == files
    assert combined[2]["quality"] == outcome


def test_replay_for_an_unrecorded_batch_is_rejected():
    with pytest.raises(ValueError, match="without a committed merge receipt"):
        _attach_replayed_quality({}, {2: {"files": [], "quality": None}})
