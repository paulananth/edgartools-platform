"""Invented complete-capture fixtures shared by native and database path proofs."""
import hashlib
import json
import zipfile


def native(name="INVENTED CO", lei="00000000000000000000", *, city="Exampleton",
           updated="2026-11-01T00:00:00+00:00"):
    address = {"FirstAddressLine": {"$": "1 Example Way"}, "City": {"$": city},
               "PostalCode": {"$": "12345"}, "Country": {"$": "US"}}
    return {"LEI": {"$": lei}, "Entity": {"LegalName": {"$": name}, "EntityCategory": {"$": "GENERAL"},
            "EntityStatus": {"$": "ACTIVE"}, "LegalAddress": address, "HeadquartersAddress": address,
            "LegalJurisdiction": {"$": "US-CA"}}, "Registration": {
            "RegistrationStatus": {"$": "ISSUED"}, "LastUpdateDate": {"$": updated}}}


def capture(folder, records, key="20260101-0000-gleif-goldencopy-lei2-golden-copy.json.zip"):
    folder.mkdir(exist_ok=True)
    with zipfile.ZipFile(folder / key, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("records.json", json.dumps({"records": records}))
    (folder / "receipts.jsonl").write_text(json.dumps({"file": key,
        "sha256": hashlib.sha256((folder / key).read_bytes()).hexdigest()}) + "\n")
    return folder
