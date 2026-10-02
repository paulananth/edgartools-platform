"""jsonl.count: write how many JSON lines the input holds."""
from __future__ import annotations

import json


def _count(data: bytes) -> int:
    return sum(1 for line in data.splitlines() if line.strip() and json.loads(line) is not None)


def execute(envelope: dict, artifacts) -> dict:
    lines = _count(artifacts.verified(envelope["input"]))
    return artifacts.put_bytes(envelope["output"], json.dumps({"lines": lines}, sort_keys=True).encode())


def verify(envelope: dict, artifacts) -> tuple[dict, list]:
    expected = {"lines": _count(artifacts.verified(envelope["input"]))}
    found = json.loads(artifacts.verified(envelope["candidate"]))
    if found != expected:
        raise ValueError("The written count differs from the input")
    return {name: True for name in envelope["checks"]}, []
