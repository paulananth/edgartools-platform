from copy import deepcopy
from datetime import datetime, timezone

import pytest

from edgar_warehouse.application import load_observer as observer


def observation(state="running"):
    return {"run_id": "00000000-0000-0000-0000-000000000001", "kind": "source",
            "name": "example", "target": "prepare", "state": state,
            "created_at": datetime(2026, 1, 1, tzinfo=timezone.utc),
            "completed_at": None, "expected_units": 2, "compacted": False,
            "checks": {}, "pending_deliveries": 0,
            "steps": [{"step": "read", "unit_state": "pending", "units": 2,
                       "attempts": 0, "errors": 0}]}


class NativeAPI:
    def __init__(self):
        self.records = []
        self.writes = 0
        self.drift = False

    def __call__(self, method, path, body=None, params=None):
        if "/name/" in path:
            return {"name": "example"}
        if method == "PUT":
            self.writes += 1
            self.records = [record for record in self.records if record['timestamp'] != body['timestamp']]
            self.records.append(deepcopy(body))
            if self.drift:
                self.records[-1]["parameters"]["bookkeeping"]["expectedUnits"] = "0"
        return {"data": self.records}


@pytest.mark.parametrize("state,native", [("running", "Pending"), ("waiting", "Pending"),
                                         ("blocked", "Failed"), ("complete", "Successful")])
def test_exact_state_survives_native_mapping(state, native):
    source = observation(state)
    if state == "complete":
        source["steps"][0]["unit_state"] = "verified"
    body = observer.payload(source, 123)
    assert body["executionStatus"] == native
    assert body["parameters"]["bookkeeping"]["state"] == state
    assert body["parameters"]["bookkeeping"]["observedAt"] == 123
    assert body["timestamp"] == 1767225600000


def test_counters_above_float_and_int64_precision_roundtrip_as_decimal_strings():
    source = observation()
    source["steps"][0]["units"] = 2**80 + 1
    body = observer.payload(source, 1)
    assert body["parameters"]["bookkeeping"]["steps"][0]["units"] == "1208925819614629174706177"
    assert body["taskStatus"] == [{"name": "read", "executionStatus": "Pending"}]


@pytest.mark.parametrize("change", ["unverified", "deliveries", "failed_check", "compacted", "missing_units"])
def test_incomplete_evidence_cannot_be_reported_as_success(change):
    source = observation("complete")
    source["steps"][0]["unit_state"] = "verified"
    if change == "unverified": source["steps"][0]["unit_state"] = "reported"
    if change == "deliveries": source["pending_deliveries"] = 1
    if change == "failed_check": source["checks"] = {"delivery": False}
    if change == "compacted": source["compacted"] = True
    if change == "missing_units": source["expected_units"] = 3
    with pytest.raises(ValueError): observer.payload(source, 1)


def test_publish_requires_readback_and_retry_replaces_same_load_record():
    api = NativeAPI()
    for now in (10, 20):
        assert observer.publish(observation(), api, service="example", observed_at=now) == "confirmed"
    assert len(api.records) == 1
    assert api.records[0]["parameters"]["bookkeeping"]["observedAt"] == 20
    api.drift = True
    with pytest.raises(ValueError, match="readback"):
        observer.publish(observation(), api, service="example", observed_at=30)


def test_colliding_loads_get_distinct_stable_keys_and_old_observations_do_not_write():
    api = NativeAPI()
    observer.publish(observation(), api, service="example", observed_at=20)
    with pytest.raises(ValueError, match="newer"):
        observer.publish(observation(), api, service="example", observed_at=10)
    other = observation(); other["run_id"] = "another-run"
    observer.publish(other, api, service="example", observed_at=30)
    observer.publish(other, api, service="example", observed_at=40)
    assert api.writes == 3
    assert len(api.records) == 2
    assert {record['timestamp'] for record in api.records} == {1767225600000, 1767225600001}


def test_dry_run_and_missing_pipeline_never_write():
    api = NativeAPI()
    assert observer.publish(observation(), api, service="example", observed_at=1, dry_run=True) == "pending"
    assert api.writes == 0
    with pytest.raises(ValueError, match="pipeline is missing"):
        observer.publish(observation(), lambda *a, **k: None, service="example", observed_at=1)


def test_discovery_pages_without_omitting_runs():
    class Book:
        def runs(self, *, limit, before):
            return {None: [{"run_id": "3"}, {"run_id": "2"}], "2": [{"run_id": "1"}]}[before]
    assert list(observer.discover(Book(), (), 2)) == ["3", "2", "1"]


def test_partial_failure_is_sanitized_and_does_not_stop_other_runs():
    class Book:
        def observation(self, identity):
            if identity == "bad": raise ConnectionError("password=secret-value")
            return observation()
    result = observer.sweep(Book(), NativeAPI(), run_ids=["bad", "good"])
    assert result["status"] == "partial"
    assert result["failed"] == 1 and result["confirmed"] == 1
    assert result["errors"] == {"ConnectionError": 1}
    assert "secret-value" not in str(result)


def test_discovery_failure_cannot_claim_complete_coverage():
    class Book:
        def runs(self, **kw): raise ConnectionError("private database address")
    result = observer.sweep(Book(), NativeAPI())
    assert result["discovery_complete"] is False
    assert result["status"] == "partial"


def test_dotted_source_uses_native_quoted_pipeline_identity():
    source = observation(); source["name"] = "example.feed"
    paths = []
    def api(method, path, body=None, params=None):
        paths.append(path)
        return {"name": "configured"} if "/name/" in path else {"data": []}
    assert observer.publish(source, api, service="example", observed_at=1, dry_run=True) == "pending"
    assert paths[0] == "/pipelines/name/example.%22source%3Aexample.feed%3Aprepare%22"


def test_readback_allows_native_defaults_but_requires_exact_values_and_types():
    expected = {"taskStatus": [{"name": "read", "executionStatus": "Pending"}], "parameters": {"count": "3"}}
    actual = {"taskStatus": [{"name": "read", "executionStatus": "Pending", "inputs": [], "outputs": []}],
              "parameters": {"count": "3"}, "inputs": []}
    assert observer.matches(expected, actual)
    actual["parameters"]["count"] = 3
    assert not observer.matches(expected, actual)


def test_second_reporter_cannot_run_with_same_lock(tmp_path, monkeypatch, capsys):
    import fcntl
    from types import SimpleNamespace
    path = tmp_path / "observer.lock"
    monkeypatch.setattr(observer, "_observe", lambda args: pytest.fail("second reporter ran"))
    with path.open("a") as lock:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        assert observer._handle(SimpleNamespace(lock_file=path)) == 1
    assert "reporter_already_running" in capsys.readouterr().out


def test_duplicate_discovery_cursor_cannot_silently_loop():
    class Book:
        def runs(self, **kw): return [{"run_id": "same"}]
    with pytest.raises(ValueError, match="repeated"):
        list(observer.discover(Book(), (), 1))


@pytest.mark.parametrize("value", [None, True, -1, 3.0])
def test_missing_or_lossy_counters_are_flagged(value):
    with pytest.raises(observer.ObservationError, match="counter"):
        observer.counter(value)


def test_declared_step_with_no_work_is_pending_until_load_completion():
    source = observation(); source['declared_steps'] = ['read', 'publish']
    body = observer.payload(source, 1)
    assert body['taskStatus'] == [{'name': 'publish', 'executionStatus': 'Pending'},
                                  {'name': 'read', 'executionStatus': 'Pending'}]
    source['state'] = 'complete'; source['steps'][0]['unit_state'] = 'verified'
    assert observer.payload(source, 2)['taskStatus'][0] == {'name': 'publish', 'executionStatus': 'Skipped'}


def test_full_native_key_window_is_refused_without_overwriting():
    api = NativeAPI()
    api.records = [{'timestamp': 1767225600000 + n, 'executionId': str(n)} for n in range(1000)]
    with pytest.raises(observer.ObservationError, match='window is full'):
        observer.publish(observation(), api, service='example', observed_at=1)
    assert api.writes == 0


def test_api_outage_and_retry_only_repeat_reporting():
    class Book:
        def observation(self, identity): return observation()
    class API(NativeAPI):
        unavailable = True
        def __call__(self, method, path, body=None, params=None):
            if method == 'PUT' and self.unavailable:
                raise ConnectionError('token=private-value')
            return super().__call__(method, path, body, params)
    api = API()
    first = observer.sweep(Book(), api, run_ids=['invented-load'])
    assert first['failed'] == 1 and first['confirmed'] == 0
    assert 'private-value' not in str(first)
    api.unavailable = False
    assert observer.sweep(Book(), api, run_ids=['invented-load'])['confirmed'] == 1
    assert api.writes == 1
