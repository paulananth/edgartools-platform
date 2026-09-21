"""Ticket 10 acceptance: re-run research 01's quality check on real DEF 14A HTML,
before and after the platform-side name repair. Research 01's definition:
'plausible person name' = no role vocabulary in the field and at least two tokens."""
import re, sys, pathlib, json
sys.path.insert(0, "/Users/aneenaananth/projects/edgartools-platform-worktrees/claude-person-ticket-10")
from lxml import html as lxml_html
from edgar.proxy.html_extractor import extract_summary_compensation
from edgar_warehouse.parsers.proxy_fundamentals import _repair_entry_names

# Research 01's role vocabulary (F1), reproducing its plausibility definition.
# NOT independent of the parser: it overlaps the parser's own vocabulary, so a
# 100% score proves the repair strips recognisable role text, NOT that the name
# it kept belongs to the right executive. Attribution is covered by the unit
# tests and by reading real before/after output, not by this score.
ROLE_VOCAB = [
    "chief", "officer", "president", "chairman", "chairwoman", "chair ", "vice",
    "executive", "general counsel", "treasurer", "secretary", "controller",
    "principal", "director", "founder", "former", "interim", "senior", "head of",
    "board", "group", "division", "finance and", "operations",
]

def plausible(name: str) -> bool:
    if not name:
        return False
    low = " " + re.sub(r"\s+", " ", name.lower().replace(".", "").replace(",", "")).strip() + " "
    if any(v in low for v in ROLE_VOCAB):
        return False
    return len([t for t in low.split() if t]) >= 2

before, after = [], []
docs = sorted(pathlib.Path(sys.argv[1]).glob("*.htm"))
parsed = 0
for doc in docs:
    try:
        tree = lxml_html.fromstring(doc.read_bytes())
        entries = extract_summary_compensation(tree) or []
    except Exception:
        continue
    if not entries:
        continue
    parsed += 1
    before += [str(e.name or "") for e in entries]
    after += [str(e.name or "") for e in _repair_entry_names(list(entries))]

def rate(names):
    ok = sum(1 for n in names if plausible(n))
    return ok, len(names), (ok / len(names) if names else 0.0)

b_ok, b_n, b_r = rate(before)
a_ok, a_n, a_r = rate(after)
print(f"documents with a Summary Compensation Table: {parsed} of {len(docs)} sampled")
print(f"BEFORE  plausible {b_ok}/{b_n} = {b_r:.1%}")
print(f"AFTER   plausible {a_ok}/{a_n} = {a_r:.1%}   (rows dropped: {b_n - a_n})")
bad_after = sorted({n for n in after if not plausible(n)})
print(f"\nremaining implausible distinct values after repair: {len(bad_after)}")
for n in bad_after[:25]:
    print("   ", repr(n))
json.dump({"docs_with_sct": parsed, "before": [b_ok, b_n, b_r], "after": [a_ok, a_n, a_r],
           "remaining_bad": bad_after[:200]},
          open(sys.argv[2], "w"), indent=2)
