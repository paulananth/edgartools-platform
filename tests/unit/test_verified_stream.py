"""Streaming parsers receive authenticated private snapshots, never live sources."""
import hashlib
import io

import pytest

from edgar_warehouse.bookkeeping.clean.artifacts import Artifacts
from edgar_warehouse.control_contract import Blocked


def ref(uri, body):
    return {"uri": uri, "sha256": hashlib.sha256(body).hexdigest()}


def test_snapshot_is_authenticated_before_entry_and_survives_source_mutation(tmp_path):
    path = tmp_path / "capture.json"
    body = b'{"records":[{}]}'
    path.write_bytes(body)
    with Artifacts().verified_stream(ref(path.as_uri(), body), max_bytes=len(body)) as stream:
        path.write_bytes(b"corrupted")
        assert stream.read() == body
        snapshot = stream
    assert snapshot.closed
    with pytest.raises(Blocked, match="hash mismatch"):
        with Artifacts().verified_stream(ref(path.as_uri(), body), max_bytes=100):
            pytest.fail("Unauthenticated bytes reached consumer")


class ShortReads(io.BytesIO):
    def __init__(self, body):
        super().__init__(body)
        self.requests = []

    def read(self, size=-1):
        assert 0 < size <= 65536
        self.requests.append(size)
        return super().read(min(size, 7))


class S3:
    def __init__(self, stream):
        self.stream = stream

    def get_object(self, **kwargs):
        assert kwargs == {"Bucket": "captured", "Key": "input.json"}
        return {"Body": self.stream}


def test_s3_short_reads_authenticate_eof_and_close_transport_before_consumer():
    body = b"abc" * 100000
    source = ShortReads(body)
    with Artifacts(S3(source)).verified_stream(ref("s3://captured/input.json", body), max_bytes=len(body)) as snapshot:
        assert source.closed
        assert snapshot.read() == body
    assert len(source.requests) > 2


def test_oversized_snapshot_refuses_without_reading_full_source():
    source = ShortReads(b"x" * 100000)
    with pytest.raises(Blocked, match="bounded snapshot"):
        with Artifacts(S3(source)).verified_stream(ref("s3://captured/input.json", b"x" * 100000), max_bytes=100):
            pytest.fail("Oversized source reached consumer")
    assert source.closed and sum(min(size, 7) for size in source.requests) == 101


def test_consumer_exception_closes_snapshot_without_reclassifying_failure(tmp_path):
    path = tmp_path / "capture"
    path.write_bytes(b"ok")
    with pytest.raises(RuntimeError, match="consumer"):
        with Artifacts().verified_stream(ref(path.as_uri(), b"ok"), max_bytes=2) as snapshot:
            raise RuntimeError("consumer")
    assert snapshot.closed


@pytest.mark.parametrize("maximum", [False, 0, -1, 1.5, 2**63])
def test_invalid_bound_refuses_before_transport(maximum):
    with pytest.raises(Blocked, match="positive signed"):
        with Artifacts(S3(None)).verified_stream(ref("s3://captured/input.json", b""), max_bytes=maximum):
            pytest.fail("Invalid bound reached consumer")
