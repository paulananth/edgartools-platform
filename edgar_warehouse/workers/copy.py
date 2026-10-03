"""artifact.copy: copy the input's bytes to the output, once."""
from __future__ import annotations

import hashlib


def execute(envelope: dict, artifacts) -> dict:
    data = artifacts.verified(envelope["input"])
    # The output store refuses to overwrite: an earlier attempt's identical
    # copy is reconciled, a different one fails the work.
    return artifacts.put_bytes(envelope["output"], data)


def verify(envelope: dict, artifacts) -> tuple[dict, list]:
    output = artifacts.read(envelope["output"])
    if not hashlib.sha256(output).hexdigest() == envelope["input"]["sha256"] == envelope["candidate"]["sha256"]:
        raise ValueError("The output is not a copy of the input")
    return {name: True for name in envelope["checks"]}, []
