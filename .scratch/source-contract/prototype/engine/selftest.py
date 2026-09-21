"""PROTOTYPE — engine self-test for the as-of lookup (ticket 04 Q3).

The local submissions copy is flat, so the Form 3/4/5 comparison cannot prove
as_of + earliest_after. This builds a dated layout (the production shape:
cik=<n>/main/YYYY/MM/DD/CIK##########.json) with two captures and checks the
selection rule directly.
"""

import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import source_engine as se  # noqa: E402

with tempfile.TemporaryDirectory() as tmp:
    root = Path(tmp)
    for day, label in (("2026/01/10", "captured-jan"), ("2026/06/10", "captured-jun")):
        p = root / "cik=123" / "main" / day / "CIK0000000123.json"
        p.parent.mkdir(parents=True)
        p.write_text(json.dumps({"entityType": label}))
    fam = {"root": str(root), "dir": "cik={int}/main", "file": "CIK{pad10}.json", "dated": True}
    sel = {"fallback": "earliest_after"}
    cases = [
        ("filed between captures → the earlier copy", "20260301", "captured-jan"),
        ("filed after both → the later copy", "20260701", "captured-jun"),
        ("filed on a capture day → that copy", "2026-06-10", "captured-jun"),
        ("filed before every capture → earliest after", "20251201", "captured-jan"),
    ]
    ok = True
    for name, as_of, want in cases:
        got = se.resolve_lookup(fam, 123, sel, as_of)["payload"]["entityType"]
        ok &= got == want
        print(f"{'ok  ' if got == want else 'FAIL'} {name}: as_of {as_of} → {got}")
    none = se.resolve_lookup(fam, 123, {"fallback": "none"}, "20251201")
    ok &= none["found"] is False
    print(f"{'ok  ' if not none['found'] else 'FAIL'} no fallback before every capture → not found")
    again = [se.resolve_lookup(fam, 123, sel, "20260301")["artifact_sha256"] for _ in range(2)]
    ok &= again[0] == again[1]
    print(f"{'ok  ' if again[0] == again[1] else 'FAIL'} repeatable: same copy, same sha256")
    sys.exit(0 if ok else 1)
