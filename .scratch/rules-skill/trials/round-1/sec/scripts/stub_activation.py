"""pytest plugin for the trial only: stands in for tests.mdm.test_clean_activation.

That module reads `.scratch/company-mastering/research/08-rules.json` at import
time, which the sandbox copy of the repo does not have. The tests under trial
import only its `proof` helper; this module provides that function and the BAR
constant, copied verbatim, and nothing else. No repo file is changed.
"""
import math
import sys
import types

from edgar_warehouse.mdm.clean.activation import wilson_lower_bound

def proof(n=3000, correct=3000, confidence=0.95, **changes):
    if "lower_bound" not in changes and 0 <= correct <= n:
        # Rounded down: a stated bound may never exceed its sample.
        changes["lower_bound"] = (
            math.floor(wilson_lower_bound(correct, n, confidence) * 1e6) / 1e6
        )
    body = {
        "method": "wilson_lower_bound",
        "one_sided_confidence": confidence,
        "n": n,
        "correct": correct,
        "lower_bound": None,
        "adversarial": {"fixture_sha256": "a" * 64, "violations": 0},
        "cohort": {
            "files": {"sample.jsonl": "b" * 64},
            # One sample per rule step, for every step id a test rule or the
            # Company policy uses ("0" to "10").
            "by_step": {
                str(step): {
                    "n": n,
                    "correct": correct,
                    "lower_bound": changes.get("lower_bound"),
                }
                for step in range(11)
            },
        },
        "approved_by": "operator",
        "approved_at": "2026-09-24T12:00:00Z",
        "reason": "fixture proof: arithmetic only, not a measurement",
    }
    body.update(changes)
    return body



_stub = types.ModuleType("tests.mdm.test_clean_activation")
_stub.proof = proof
_stub.BAR = {
    "min_precision": 0.999,
    "method": "wilson_lower_bound",
    "one_sided_confidence": 0.95,
}  # verbatim from tests/mdm/test_clean_activation.py lines 55-59
sys.modules["tests.mdm.test_clean_activation"] = _stub
