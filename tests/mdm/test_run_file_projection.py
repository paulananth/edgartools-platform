"""A target may declare, per run file, the parts of it that count as its content (ticket 177, slice 3):
the processing identity then moves only when those parts change, not with the rest of the file
(the capture it was built from, say). Every name here is invented."""
import json
from copy import deepcopy

import pytest

from edgar_warehouse.mdm import target_manifest
from edgar_warehouse.rules import files
from tests.mdm import test_ownership_target as ownership

BASE = {"entries": [1, 2, 3], "version": 1, "built_from": "capture-a"}


def identity(monkeypatch, tmp_path, body=BASE, *, projections=None, files_declared=("shared_counts",)):
    real = files.source

    def source(name, *args, **kwargs):
        reading = deepcopy(real(name, *args, **kwargs))
        if name == ownership.SOURCE:
            run = {"facts": [], "files": list(files_declared)}
            if projections is not None:
                run["projections"] = projections
            reading["bookkeeping"]["targets"]["mastering"]["run"] = run
        return reading
    monkeypatch.setattr(target_manifest.rules_files, "source", source)
    tmp_path.mkdir(parents=True, exist_ok=True)
    path = tmp_path / "shared_counts.json"
    path.write_text(json.dumps(body))
    options = ownership.capture(tmp_path, [1])
    return target_manifest.write_manifest(**options, facts={}, run_files={"shared_counts": str(path)})["scope"]["processing_identity"]


def test_a_part_outside_the_projection_does_not_move_the_identity(monkeypatch, tmp_path):
    projection = {"shared_counts": ["entries", "version"]}
    first = identity(monkeypatch, tmp_path / "a", projections=projection)
    second = identity(monkeypatch, tmp_path / "b", {**BASE, "built_from": "capture-b"}, projections=projection)
    assert first == second


def test_a_part_inside_the_projection_moves_it(monkeypatch, tmp_path):
    projection = {"shared_counts": ["entries", "version"]}
    first = identity(monkeypatch, tmp_path / "a", projections=projection)
    assert first != identity(monkeypatch, tmp_path / "b", {**BASE, "entries": [1, 2]}, projections=projection)


def test_without_a_projection_the_whole_file_counts(monkeypatch, tmp_path):
    first = identity(monkeypatch, tmp_path / "a")
    assert first != identity(monkeypatch, tmp_path / "b", {**BASE, "built_from": "capture-b"})


@pytest.mark.parametrize("projections, body, message", [
    ({"other": ["entries"]}, BASE, "projection names a file"),            # a file the run does not declare
    ({"shared_counts": []}, BASE, "projection of run file"),                    # an empty projection
    ({"shared_counts": ["entries", "entries"]}, BASE, "projection of run file"),  # a repeated part
    ({"shared_counts": ["missing"]}, BASE, "has no part"),                # a part the file lacks
    ({"shared_counts": ["entries"]}, [1, 2], "has no part|not an object"),  # a file that is not an object
])
def test_a_bad_projection_is_refused(monkeypatch, tmp_path, projections, body, message):
    with pytest.raises(Exception, match=message):
        identity(monkeypatch, tmp_path, body, projections=projections)
