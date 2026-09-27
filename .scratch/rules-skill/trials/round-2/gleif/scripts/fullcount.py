"""Lean full pass over one GLEIF member: only the counts that decide something.

Usage: fullcount.py <member: level1|relationships|reporting_exceptions> <zip> <limit|0> <out.json>

It mirrors the checks `gleif_source.record_evidence` makes before `normalize`,
without scope (every record is treated as in scope), to count how many records
each deferral reason would hit.
"""

import json
import sys
import time
import zipfile
from collections import Counter

import ijson

from edgar_warehouse.mdm.clean.adapters import UnsupportedRecord, format_value
from edgar_warehouse.mdm.clean.evidence import instant
from edgar_warehouse.mdm.clean.gleif_source import EXCEPTION_REASONS

WRAPPER = {"level1": "records", "relationships": "relations", "reporting_exceptions": "exceptions"}
CATEGORIES = {"GENERAL", "BRANCH", "FUND", "SOLE_PROPRIETOR",
              "INTERNATIONAL_ORGANIZATION", "RESIDENT_GOVERNMENT_ENTITY"}


def v(node, path):
    for part in path.split("."):
        if not isinstance(node, dict):
            return None
        node = node.get(part)
    return node


def lei_reason(value):
    try:
        format_value(value, "lei")
        return None
    except UnsupportedRecord as exc:
        return exc.reason


def level1(r, c, examples):
    lei = v(r, "LEI.$")
    reason = lei_reason(lei)
    cat = v(r, "Entity.EntityCategory.$")
    c["category"][cat] += 1
    c["entity_status"][v(r, "Entity.EntityStatus.$")] += 1
    c["registration_status"][v(r, "Registration.RegistrationStatus.$")] += 1
    c["category_x_entity_status"][f"{cat}|{v(r, 'Entity.EntityStatus.$')}"] += 1
    if reason:
        c["reason"][reason] += 1
        c["bad_lei_by_status"][f"{cat}|{v(r, 'Entity.EntityStatus.$')}|{v(r, 'Registration.RegistrationStatus.$')}"] += 1
        if len(examples) < 15:
            examples.append([lei, v(r, "Entity.LegalName.$"), v(r, "Registration.RegistrationStatus.$")])
    elif cat not in CATEGORIES:
        c["reason"]["invalid_identity_kind"] += 1
    else:
        c["reason"]["normalize (then kind/scope)"] += 1
    ra = v(r, "Entity.RegistrationAuthority.RegistrationAuthorityID.$")
    rid = v(r, "Entity.RegistrationAuthority.RegistrationAuthorityEntityID.$")
    c["ra"][ra] += 1
    if isinstance(rid, str) and rid.isdigit() and len(rid) <= 10:
        c["ra_digit_ids"][ra] += 1
    # shapes that the mapping language must cope with
    add = v(r, "Entity.HeadquartersAddress.AdditionalAddressLine")
    c["hq_additional_line_type"][type(add).__name__] += 1
    for f in ("Entity.LegalName.$", "Entity.LegalJurisdiction.$", "Registration.LastUpdateDate.$",
              "Entity.HeadquartersAddress.PostalCode.$", "Entity.HeadquartersAddress.Country.$",
              "Entity.LegalForm.EntityLegalFormCode.$", "Entity.EntityCreationDate.$"):
        if v(r, f) in (None, ""):
            c["empty"][f] += 1


def relationships(r, c, keys):
    row = r.get("RelationshipRecord", {})
    start, end = v(row, "Relationship.StartNode.NodeID.$"), v(row, "Relationship.EndNode.NodeID.$")
    rtype = v(row, "Relationship.RelationshipType.$")
    c["type"][rtype] += 1
    c["status"][v(row, "Relationship.RelationshipStatus.$")] += 1
    c["registration_status"][v(row, "Registration.RegistrationStatus.$")] += 1
    keys["start_end_type"][(start, end, rtype)] += 1
    keys["start_type"][(start, rtype)] += 1
    reason = lei_reason(start) or lei_reason(end)
    if not reason and any(v(row, f"Relationship.{s}.NodeIDType.$") != "LEI" for s in ("StartNode", "EndNode")):
        reason = "unsupported_relationship_endpoint"
    if not reason:
        periods = v(row, "Relationship.RelationshipPeriods.RelationshipPeriod")
        periods = periods if isinstance(periods, list) else [periods]
        rp = [p for p in periods if isinstance(p, dict) and v(p, "PeriodType.$") == "RELATIONSHIP_PERIOD"]
        c["relationship_period_count"][len(rp)] += 1
        if len(rp) != 1:
            reason = "ambiguous_relationship_period"
        else:
            s_at, e_at = v(rp[0], "StartDate.$"), v(rp[0], "EndDate.$")
            status = v(row, "Relationship.RelationshipStatus.$")
            try:
                if not s_at or (e_at and instant(s_at) >= instant(e_at)):
                    reason = "invalid_relationship_interval"
                elif status not in {"ACTIVE", "INACTIVE"} or (status == "INACTIVE" and not e_at):
                    reason = "invalid_relationship_status_interval"
            except ValueError:
                reason = "invalid_native_field"
    c["reason"][reason or "normalize (then scope)"] += 1
    if reason:
        c["reason_x_type"][f"{reason}|{rtype}"] += 1


def reporting_exceptions(r, c, _):
    reason = lei_reason(v(r, "LEI.$"))
    cat = v(r, "ExceptionCategory.$")
    c["category"][cat] += 1
    reasons = r.get("ExceptionReason")
    reasons = reasons if isinstance(reasons, list) else [reasons]
    for x in reasons:
        c["exception_reason"][v(x, "$") if isinstance(x, dict) else repr(x)] += 1
    c["reasons_per_record"][len(reasons)] += 1
    if not reason:
        if cat not in {"DIRECT_ACCOUNTING_CONSOLIDATION_PARENT", "ULTIMATE_ACCOUNTING_CONSOLIDATION_PARENT"}:
            reason = "unsupported_exception_category"
        elif not r.get("ExceptionReason"):
            reason = "missing_exception_reason"
        elif any(not isinstance(x, dict) or x.get("$") not in EXCEPTION_REASONS for x in reasons):
            reason = "invalid_exception_reason"
        else:
            reason = "reported_parent_exception"
    c["reason"][reason] += 1


def main(member, zip_path, limit, out):
    limit = int(limit)
    c = {k: Counter() for k in ("category", "entity_status", "registration_status", "reason", "type",
                                 "status", "exception_reason", "reasons_per_record", "ra", "ra_digit_ids",
                                 "bad_lei_by_status", "relationship_period_count", "reason_x_type",
                                 "category_x_entity_status", "hq_additional_line_type", "empty")}
    keys = {"start_end_type": Counter(), "start_type": Counter()}
    examples = []
    fn = {"level1": level1, "relationships": relationships, "reporting_exceptions": reporting_exceptions}[member]
    n, t0 = 0, time.time()
    with zipfile.ZipFile(zip_path) as z, z.open(z.infolist()[0]) as f:
        for r in ijson.items(f, f"{WRAPPER[member]}.item", use_float=True):
            fn(r, c, keys if member == "relationships" else examples)
            n += 1
            if limit and n >= limit:
                break
    result = {"member": member, "records": n, "seconds": round(time.time() - t0, 1),
              **{k: dict(val.most_common(40)) for k, val in c.items() if val}, "examples": examples}
    if member == "relationships":
        result["dup_start_end_type"] = sum(1 for x in keys["start_end_type"].values() if x > 1)
        result["dup_start_type"] = sum(1 for x in keys["start_type"].values() if x > 1)
        result["dup_start_type_by_type"] = dict(Counter(k[1] for k, x in keys["start_type"].items() if x > 1))
    json.dump(result, open(out, "w"), indent=1, default=str)
    print(json.dumps({k: result[k] for k in ("member", "records", "seconds")}))


if __name__ == "__main__":
    main(*sys.argv[1:])
