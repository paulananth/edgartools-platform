"""Ticket 08: pull every GLEIF Level 1 record whose registration or validation
authority is RA000665, with the fields a matching rule compares.

Reads the pinned local Golden Copy (2026-09-11 16:00 UTC, sha256 1b6cd9cd...).
No network. Usage: python 08-extract-gleif-ra000665.py <lei2.json.zip> <out.jsonl>
"""

import json
import subprocess
import sys

import ijson

archive, out_path = sys.argv[1], sys.argv[2]


def text(node):
    return node.get("$") if isinstance(node, dict) else None


proc = subprocess.Popen(["unzip", "-p", archive], stdout=subprocess.PIPE)
seen = kept = 0
with open(out_path, "w") as out:
    for rec in ijson.items(proc.stdout, "records.item"):
        seen += 1
        ent = rec.get("Entity", {})
        reg = rec.get("Registration", {})
        ra = ent.get("RegistrationAuthority", {}) or {}
        va = reg.get("ValidationAuthority", {}) or {}
        ra_id = text(ra.get("RegistrationAuthorityID", {}))
        va_id = text(va.get("ValidationAuthorityID", {}))
        if "RA000665" not in (ra_id, va_id):
            continue
        kept += 1
        out.write(
            json.dumps(
                {
                    "lei": text(rec.get("LEI", {})),
                    "ra_id": ra_id,
                    "ra_entity_id": text(ra.get("RegistrationAuthorityEntityID", {})),
                    "va_id": va_id,
                    "va_entity_id": text(va.get("ValidationAuthorityEntityID", {})),
                    "legal_name": text(ent.get("LegalName", {})),
                    "category": text(ent.get("EntityCategory", {})),
                    "legal_form": text(
                        (ent.get("LegalForm", {}) or {}).get("EntityLegalFormCode", {})
                    ),
                    "jurisdiction": text(ent.get("LegalJurisdiction", {})),
                    "entity_status": text(ent.get("EntityStatus", {})),
                    "registration_status": text(reg.get("RegistrationStatus", {})),
                    "hq_country": text(
                        (ent.get("HeadquartersAddress", {}) or {}).get("Country", {})
                    ),
                    "hq_postal": text(
                        (ent.get("HeadquartersAddress", {}) or {}).get("PostalCode", {})
                    ),
                },
                default=str,
            )
            + "\n"
        )
proc.wait()
print(json.dumps({"records_seen": seen, "ra000665_records": kept}))
