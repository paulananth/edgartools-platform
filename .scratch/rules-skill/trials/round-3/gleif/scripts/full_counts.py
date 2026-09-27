"""Full-pass counts that decide something, per member. Line-split + json.loads.

Usage: full_counts.py <member rr|repex|level1> <zip> <out.json>
Timed on the sample first (json.loads of 9000 sample records: ~0.3 s).
"""

from __future__ import annotations

import collections
import io
import json
import re
import sys
import time
import zipfile
from datetime import datetime

LEI_RE = re.compile(r"[A-Z0-9]{18}[0-9]{2}")


def lei_ok(v) -> bool:
    if not isinstance(v, str) or not LEI_RE.fullmatch(v):
        return False
    digits = "".join(str(ord(c) - 55) if c.isalpha() else c for c in v)
    return int(digits) % 97 == 1


def tz_ok(v) -> str:
    if not isinstance(v, str):
        return "missing" if v is None else "not_text"
    try:
        d = datetime.fromisoformat(v)
    except ValueError:
        return "unparseable"
    return "tz" if d.tzinfo is not None else "no_tz"


def g(row, path):
    for p in path.split("."):
        if not isinstance(row, dict):
            return None
        row = row.get(p)
    return row


def records(path):
    with zipfile.ZipFile(path) as z:
        info = z.infolist()[0]
        f = io.BufferedReader(z.open(info), buffer_size=4 << 20)
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
                if s == b"},":
                    text = text[:-1]
                elif s == b"}]}":
                    text = text[:-2]
                yield json.loads(text)
                cur = None


C = collections.Counter


def rr(path):
    out = collections.defaultdict(C)
    keys = collections.Counter()
    direct_active = collections.defaultdict(set)
    n = 0
    for rec in records(path):
        n += 1
        r = rec.get("RelationshipRecord", {})
        start = g(r, "Relationship.StartNode.NodeID.$")
        end = g(r, "Relationship.EndNode.NodeID.$")
        typ = g(r, "Relationship.RelationshipType.$")
        status = g(r, "Relationship.RelationshipStatus.$")
        keys[(start, end, typ)] += 1
        out["type"][typ] += 1
        out["type_x_status"][f"{typ}|{status}"] += 1
        out["registration_status"][g(r, "Registration.RegistrationStatus.$")] += 1
        out["start_type"][g(r, "Relationship.StartNode.NodeIDType.$")] += 1
        out["end_type"][g(r, "Relationship.EndNode.NodeIDType.$")] += 1
        out["start_lei_ok"][lei_ok(start)] += 1
        out["end_lei_ok"][lei_ok(end)] += 1
        out["top_keys"][",".join(sorted(rec))] += 1
        out["record_keys"][",".join(sorted(r))] += 1
        out["extension"][json.dumps(rec.get("Extension", r.get("Extension")), sort_keys=True)[:80]] += 1
        periods = g(r, "Relationship.RelationshipPeriods.RelationshipPeriod")
        periods = periods if isinstance(periods, list) else [periods]
        rel = [p for p in periods if isinstance(p, dict) and g(p, "PeriodType.$") == "RELATIONSHIP_PERIOD"]
        out["relationship_period_count"][len(rel)] += 1
        if len(rel) == 1:
            sa, ea = g(rel[0], "StartDate.$"), g(rel[0], "EndDate.$")
            out["start_tz"][tz_ok(sa)] += 1
            out["end_tz"][tz_ok(ea)] += 1
            if status == "INACTIVE" and not ea:
                out["inactive_without_end"][typ] += 1
            if status == "ACTIVE" and ea:
                out["active_with_end"][typ] += 1
            if sa and ea and tz_ok(sa) == tz_ok(ea) == "tz":
                if datetime.fromisoformat(sa) >= datetime.fromisoformat(ea):
                    out["start_not_before_end"][typ] += 1
        out["last_update_tz"][tz_ok(g(r, "Registration.LastUpdateDate.$"))] += 1
        out["qualifier_dims"][json.dumps(g(r, "Relationship.RelationshipQualifiers"), sort_keys=True)[:120] if g(r, "Relationship.RelationshipQualifiers") else None] += 0
        q = g(r, "Relationship.RelationshipQualifiers.RelationshipQualifier") or []
        for item in q if isinstance(q, list) else [q]:
            out["qualifier"][f"{g(item,'QualifierDimension.$')}={g(item,'QualifierCategory.$')}"] += 1
        qq = g(r, "Relationship.RelationshipQuantifiers.RelationshipQuantifier") or []
        for item in qq if isinstance(qq, list) else [qq]:
            out["quantifier"][f"{g(item,'MeasurementMethod.$')}|{g(item,'QuantifierUnits.$')}"] += 1
        if typ == "IS_DIRECTLY_CONSOLIDATED_BY" and status == "ACTIVE":
            direct_active[start].add(end)
    dup = {k: v for k, v in keys.items() if v > 1}
    report = {k: dict(v.most_common(60)) for k, v in out.items()}
    report["records"] = n
    report["distinct_start_end_type"] = len(keys)
    report["duplicate_start_end_type_keys"] = len(dup)
    report["duplicate_examples"] = [list(k) + [v] for k, v in list(dup.items())[:10]]
    report["starts_with_several_active_direct_parents"] = sum(1 for v in direct_active.values() if len(v) > 1)
    return report


def repex(path):
    out = collections.defaultdict(C)
    keys = collections.Counter()
    n = 0
    for rec in records(path):
        n += 1
        lei = g(rec, "LEI.$")
        cat = g(rec, "ExceptionCategory.$")
        keys[(lei, cat)] += 1
        deleted = isinstance(rec.get("Extension"), dict) and "gleif:Deletion" in rec["Extension"]
        out["category"][cat] += 1
        out["deleted"][f"{cat}|{deleted}"] += 1
        reasons = rec.get("ExceptionReason")
        reasons = reasons if isinstance(reasons, list) else [reasons]
        out["reason_count"][len(reasons)] += 1
        for x in reasons:
            out["reason"][f"{cat}|{g(x, '$') if isinstance(x, dict) else x}"] += 1
        out["lei_ok"][lei_ok(lei)] += 1
        out["top_keys"][",".join(sorted(rec))] += 1
        out["extension"][json.dumps(rec.get("Extension"), sort_keys=True)[:80]] += 1
        if rec.get("ExceptionReference"):
            out["has_reference"][cat] += 1
    dup = {k: v for k, v in keys.items() if v > 1}
    report = {k: dict(v.most_common(60)) for k, v in out.items()}
    report["records"] = n
    report["distinct_lei_category"] = len(keys)
    report["duplicate_lei_category_keys"] = len(dup)
    report["duplicate_examples"] = [list(k) + [v] for k, v in list(dup.items())[:10]]
    report["distinct_leis"] = len({k[0] for k in keys})
    return report


def level1(path):
    out = collections.defaultdict(C)
    leis = set()
    dup = 0
    n = 0
    for rec in records(path):
        n += 1
        lei = g(rec, "LEI.$")
        if lei in leis:
            dup += 1
        leis.add(lei)
        e = rec.get("Entity", {})
        reg = rec.get("Registration", {})
        cat = g(e, "EntityCategory.$")
        out["lei_ok"][lei_ok(lei)] += 1
        out["category"][cat] += 1
        out["subcategory"][f"{cat}|{g(e, 'EntitySubCategory.$')}"] += 1
        out["entity_status"][f"{cat}|{g(e, 'EntityStatus.$')}"] += 1
        out["registration_status"][g(reg, "RegistrationStatus.$")] += 1
        out["last_update_tz"][tz_ok(g(reg, "LastUpdateDate.$"))] += 1
        ra = g(e, "RegistrationAuthority.RegistrationAuthorityID.$")
        out["ra_top"][ra] += 1
        raid = g(e, "RegistrationAuthority.RegistrationAuthorityEntityID.$")
        if ra == "RA000665":
            shape = "none" if raid is None else "digits" if str(raid).isdigit() else re.sub(r"[0-9]", "9", re.sub(r"[A-Za-z]", "A", str(raid)))[:14]
            out["ra000665_id_shape"][shape] += 1
            out["ra000665_category"][cat] += 1
        out["elf_placeholder"][g(e, "LegalForm.EntityLegalFormCode.$") == "8888"] += 1
        out["jurisdiction_shape"][re.sub(r"[A-Z]", "A", g(e, "LegalJurisdiction.$") or "<none>")] += 1
        out["legal_name_type"][type(g(e, "LegalName.$")).__name__] += 1
        out["hq_postcode_type"][type(g(e, "HeadquartersAddress.PostalCode.$")).__name__] += 1
        out["hq_country_type"][type(g(e, "HeadquartersAddress.Country.$")).__name__] += 1
        out["legal_postcode_type"][type(g(e, "LegalAddress.PostalCode.$")).__name__] += 1
        out["validation_sources_type"][type(g(reg, "ValidationSources.$")).__name__] += 1
        out["conformity"][g(reg, "ConformityFlag.$")] += 1
        out["extension_keys"][",".join(sorted((rec.get("Extension") or {}).keys())) if isinstance(rec.get("Extension"), dict) else str(type(rec.get("Extension")).__name__)] += 1
        out["top_keys"][",".join(sorted(rec))] += 1
        out["successor"][bool(e.get("SuccessorEntity"))] += 1
        out["events"][bool(e.get("LegalEntityEvents"))] += 1
        out["associated"][bool(e.get("AssociatedEntity"))] += 1
        out["managing_lou_ok"][lei_ok(g(reg, "ManagingLOU.$"))] += 1
    report = {k: dict(v.most_common(80)) for k, v in out.items()}
    report["records"] = n
    report["distinct_leis"] = len(leis)
    report["duplicate_leis"] = dup
    return report


def main():
    member, path, out_path = sys.argv[1:4]
    t = time.time()
    report = {"rr": rr, "repex": repex, "level1": level1}[member](path)
    report["seconds"] = round(time.time() - t, 1)
    with open(out_path, "w") as fh:
        json.dump(report, fh, indent=1, default=str)
    print(json.dumps({"member": member, "records": report["records"], "seconds": report["seconds"]}))


if __name__ == "__main__":
    main()
