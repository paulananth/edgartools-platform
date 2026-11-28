"""The OpenFIGI ticker capture asks only for the tickers no Security holds, and writes a capture the OpenFIGI load reads."""
import hashlib
import importlib.util
import json
from pathlib import Path

import pytest

PATH = Path(__file__).resolve().parents[2] / "scripts/dev/openfigi_ticker_capture.py"
spec = importlib.util.spec_from_file_location("openfigi_ticker_capture", PATH)
tool = importlib.util.module_from_spec(spec)
spec.loader.exec_module(tool)


DATED = "company_tickers_exchange/2026/09/02/company_tickers_exchange.json"


def sec_tickers(root: Path, body: bytes) -> Path:
    """The SEC's ticker file in its dated folder, as the SEC capture keeps it."""
    path = root / "sec" / DATED
    path.parent.mkdir(parents=True)
    path.write_bytes(body)
    return path


def test_the_sec_ticker_file_keeps_its_dated_folder_and_one_outside_one_is_refused(tmp_path):
    assert tool.sec_file(sec_tickers(tmp_path, b"{}")) == DATED
    with pytest.raises(ValueError, match="dated"):
        tool.sec_file(tmp_path / "company_tickers_exchange.json")


def test_it_asks_each_ticker_no_security_holds_once_as_written_and_compares_it_as_a_security_holds_it():
    stated = ["ABCD", "abcd", "EF.G", "HI.J", "HELD", None, "", ".", "ZZ"]

    assert tool.wanted(stated, held={"HELD", "EFG"}) == ["ABCD", "HI.J", "ZZ"]


def test_a_capture_holds_batches_of_one_hundred_us_ticker_jobs_and_the_sec_ticker_file(tmp_path):
    sec_file = sec_tickers(tmp_path, b'{"fields": [], "data": []}')
    folder = tmp_path / "capture"

    tool.write(folder, [f"T{n:03d}" for n in range(250)], sec_file)

    requests = sorted((folder / "id_ticker").glob("*.request.json"))
    assert [p.name for p in requests] == ["00000.request.json", "00001.request.json", "00002.request.json"]
    jobs = [json.loads(p.read_bytes()) for p in requests]
    assert [len(batch) for batch in jobs] == [100, 100, 50]
    assert jobs[0][0] == {"exchCode": "US", "idType": "TICKER", "idValue": "T000"}
    assert (folder / DATED).read_bytes() == sec_file.read_bytes()


def test_a_capture_folder_is_never_written_twice(tmp_path):
    sec_file = sec_tickers(tmp_path, b"{}")
    tool.write(tmp_path / "capture", ["ABC"], sec_file)

    with pytest.raises(FileExistsError):
        tool.write(tmp_path / "capture", ["XYZ"], sec_file)


def test_each_answer_is_kept_beside_its_request_with_a_receipt_naming_both_digests(tmp_path):
    sec_file = sec_tickers(tmp_path, b"{}")
    folder = tmp_path / "capture"
    tool.write(folder, ["ABC", "XYZ"], sec_file)
    sent = []

    def post(body: bytes) -> bytes:
        sent.append(body)
        return b'[{"data": []}, {"warning": "No identifier found."}]'

    tool.send(folder, post)

    request = (folder / "id_ticker/00000.request.json").read_bytes()
    answer = (folder / "id_ticker/00000.json").read_bytes()
    assert sent == [request]
    receipts = [json.loads(line) for line in (folder / "receipts.jsonl").read_text().splitlines()]
    assert receipts == [
        {"file": "id_ticker/00000.json", "status": 200, "bytes": len(answer),
         "sha256": hashlib.sha256(answer).hexdigest(), "request_sha256": hashlib.sha256(request).hexdigest()},
        {"file": DATED, "status": 200, "bytes": 2, "sha256": hashlib.sha256(b"{}").hexdigest()},
    ]


def test_an_answer_that_does_not_answer_every_job_is_refused_and_writes_no_receipts(tmp_path):
    sec_file = sec_tickers(tmp_path, b"{}")
    folder = tmp_path / "capture"
    tool.write(folder, ["ABC", "XYZ"], sec_file)

    with pytest.raises(ValueError, match="answers 1 of 2"):
        tool.send(folder, lambda body: b'[{"data": []}]')
    assert not (folder / "receipts.jsonl").exists()
