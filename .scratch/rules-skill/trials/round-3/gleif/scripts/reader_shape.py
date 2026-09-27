"""Records in the reader's shape, built from gleif_source.record_evidence (lines 405-448).
RR rows are reshaped exactly as the reader does; L1/REPEX rows are the native record plus `_native`."""
import json, sys
sys.path.insert(0, ".")
from edgar_warehouse.mdm.clean.adapters import value, format_value
from edgar_warehouse.mdm.clean.evidence import instant
sb = sys.argv[1]
def rr_shape(raw):
    row = raw.get("RelationshipRecord", {})
    periods = value(row, "Relationship.RelationshipPeriods.RelationshipPeriod")
    periods = periods if isinstance(periods, list) else [periods]
    periods = [p for p in periods if isinstance(p, dict) and value(p, "PeriodType.$") == "RELATIONSHIP_PERIOD"]
    s, e = value(periods[0], "StartDate.$"), value(periods[0], "EndDate.$")
    return {"start": format_value(value(row, "Relationship.StartNode.NodeID.$"), "lei"),
            "end": format_value(value(row, "Relationship.EndNode.NodeID.$"), "lei"),
            "relationship_type": value(row, "Relationship.RelationshipType.$"),
            "valid_from": instant(s).isoformat(), "valid_to": instant(e).isoformat() if e else None,
            "status": value(row, "Relationship.RelationshipStatus.$"),
            "registration_status": value(row, "Registration.RegistrationStatus.$"),
            "_native": "<the raw RelationshipRecord, as above>"}
rr = json.load(open(f"{sb}/scratch/profile-rr.json"))["examples"]
out = {"rr": [rr_shape(r) for seg in ("start", "middle", "end") for r in rr[seg][:2]]}
l1 = json.load(open(f"{sb}/scratch/profile-l1.json"))["examples"]
r = l1["middle"][0]
out["level1_top_keys"] = sorted({**r, "_native": None})
out["level1_example_selected_paths"] = {p: value(r, p) for p in [
  "LEI.$", "Entity.LegalName.$", "Entity.EntityCategory.$", "Entity.LegalJurisdiction.$",
  "Entity.HeadquartersAddress.PostalCode.$", "Entity.HeadquartersAddress.Country.$",
  "Entity.HeadquartersAddress.AdditionalAddressLine", "Entity.LegalForm.EntityLegalFormCode.$",
  "Entity.EntityStatus.$", "Registration.RegistrationStatus.$", "Registration.LastUpdateDate.$",
  "Entity.RegistrationAuthority.RegistrationAuthorityID.$", "Entity.RegistrationAuthority.RegistrationAuthorityEntityID.$"]}
print(json.dumps(out, indent=1, ensure_ascii=False))
