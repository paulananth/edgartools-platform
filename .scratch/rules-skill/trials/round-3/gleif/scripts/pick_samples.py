"""Stream each captured zip and keep a handful of records chosen to exercise each mapping path
and each deferral reason. Stops early once every target is filled. Writes scratch/samples/<member>.jsonl
(one raw native record per line, exactly as the file holds it)."""

import io
import json
import os
import sys
import zipfile

SB = sys.argv[1]
INP = f"{SB}/inputs"
OUT = f"{SB}/scratch/samples"
os.makedirs(OUT, exist_ok=True)
FILES = {
    "level1": "01-20260911-1600-gleif-goldencopy-lei2-golden-copy.json.zip",
    "relationships": "01-20260911-1600-gleif-goldencopy-rr-golden-copy.json.zip",
    "reporting_exceptions": "01-20260911-1600-gleif-goldencopy-repex-golden-copy.json.zip",
}


def g(row, path):
    for p in path.split("."):
        if not isinstance(row, dict):
            return None
        row = row.get(p)
    return row


def records(path):
    with zipfile.ZipFile(path) as z:
        f = io.BufferedReader(z.open(z.infolist()[0]), buffer_size=4 << 20)
        f.readline()
        cur = None
        for line in f:
            if cur is None:
                if line.rstrip(b"\r\n") == b"{":
                    cur = [line]
                continue
            cur.append(line)
            s = line.rstrip(b"\r\n")
            if s in (b"}", b"},", b"}]}"):
                text = b"".join(cur).rstrip(b"\r\n")
                text = text[:-1] if s == b"}," else text[:-2] if s == b"}]}" else text
                yield json.loads(text)
                cur = None


def l1_target(r):
    e = r["Entity"]
    cat = g(e, "EntityCategory.$")
    lei = g(r, "LEI.$")
    if lei == "0292001629A3Q7XJ0D13":
        return "bad_lei"
    if cat == "GENERAL" and e.get("LegalAddress", {}).get("AdditionalAddressLine"):
        return "general_with_street2"
    if cat == "GENERAL" and g(e, "LegalForm.EntityLegalFormCode.$") == "8888":
        return "general_8888"
    if cat == "GENERAL" and g(e, "EntityStatus.$") == "NULL":
        return "general_status_null"
    if cat == "GENERAL" and g(e, "RegistrationAuthority.RegistrationAuthorityID.$") == "RA000665":
        return "general_sec_ra"
    if cat == "GENERAL":
        return "general_plain"
    return {"FUND": "fund", "BRANCH": "branch", "SOLE_PROPRIETOR": "sole_proprietor",
            "RESIDENT_GOVERNMENT_ENTITY": "government",
            "INTERNATIONAL_ORGANIZATION": "international_org"}.get(cat)


def rr_target(r):
    rel = r["RelationshipRecord"]["Relationship"]
    typ, status = g(rel, "RelationshipType.$"), g(rel, "RelationshipStatus.$")
    periods = g(rel, "RelationshipPeriods.RelationshipPeriod")
    if g(rel, "StartNode.NodeID.$") == "4469000001BG7ASKSB18":
        return "bad_lei"
    if periods is None:
        return "no_period"
    if status == "NULL":
        return "status_null"
    if status == "INACTIVE" and "CONSOLIDATED" in typ:
        return "consolidation_inactive"
    if typ == "IS_DIRECTLY_CONSOLIDATED_BY" and isinstance(periods, list):
        return "direct_multi_period"
    return {"IS_DIRECTLY_CONSOLIDATED_BY": "direct", "IS_ULTIMATELY_CONSOLIDATED_BY": "ultimate",
            "IS_FUND-MANAGED_BY": "fund_managed", "IS_INTERNATIONAL_BRANCH_OF": "branch"}.get(typ)


def rx_target(r):
    if g(r, "LEI.$") == "4469000001BG7ASKSB18":
        return "bad_lei"
    if isinstance(r.get("Extension"), dict) and "gleif:Deletion" in r["Extension"]:
        return "deleted_marker"
    if r.get("ExceptionReference"):
        return "with_reference"
    return f"plain_{g(r, 'ExceptionCategory.$')}"


PLAN = {
    "level1": (l1_target, {"bad_lei": 1, "general_with_street2": 2, "general_8888": 1,
                           "general_status_null": 1, "general_sec_ra": 1, "general_plain": 2,
                           "fund": 1, "branch": 1, "sole_proprietor": 1, "government": 1,
                           "international_org": 1}),
    "relationships": (rr_target, {"bad_lei": 1, "no_period": 1, "status_null": 1,
                                  "consolidation_inactive": 1, "direct_multi_period": 1,
                                  "direct": 2, "ultimate": 2, "fund_managed": 1, "branch": 1}),
    "reporting_exceptions": (rx_target, {"bad_lei": 1, "deleted_marker": 1, "with_reference": 1,
                                         "plain_DIRECT_ACCOUNTING_CONSOLIDATION_PARENT": 2,
                                         "plain_ULTIMATE_ACCOUNTING_CONSOLIDATION_PARENT": 1}),
}

member = sys.argv[2]
fn, want = PLAN[member]
got = {k: [] for k in want}
seen = 0
for rec in records(f"{INP}/{FILES[member]}"):
    seen += 1
    t = fn(rec)
    if t in got and len(got[t]) < want[t]:
        got[t].append(rec)
        if all(len(got[k]) >= want[k] for k in want):
            break
with open(f"{OUT}/{member}.jsonl", "w") as fh:
    for t, recs in got.items():
        for r in recs:
            fh.write(json.dumps({"target": t, "record": r}, ensure_ascii=False) + "\n")
print(member, "records streamed:", seen, {k: len(v) for k, v in got.items()})
