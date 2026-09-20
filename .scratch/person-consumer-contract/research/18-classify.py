#!/usr/bin/env python3
"""Ticket 18 -- reporting-owner classification precision (Form 3/4/5 -> person vs entity).

Three stages, all deterministic, all re-runnable:

  parse   read every bronze `filing_artifact/<sha256>` object (full SEC .txt submission:
          SGML header + <ownershipDocument> XML), emit one JSONL row per reporting owner,
          joined to the owner CIK's latest bronze `submissions/sec/cik=<cik>/main/...` payload.
  sample  draw a stratified sample of distinct owner CIKs (flag combination x entity-token
          presence) with a draft label + the evidence the human labeler reads.
  score   apply every candidate rule to the labeled sample and to the full row population,
          report precision of the automatic person / entity decisions, deferral share and
          Wilson 95% intervals; write the summary JSON.

Run with:  uv run --no-project --with edgartools python 18-classify.py <stage> [args]
(edgartools 5.58.0 is imported only for `edgar.entity.constants._classify_is_individual`, the
package's own 9-signal owner classifier, which is scored here as candidate R6 against the
bronze `submissions.json` snapshot. The repo parser -- edgar_warehouse/parsers/ownership.py ->
`Ownership.from_xml` -- is deliberately NOT used: `edgar/ownership/owners.py:117` calls
`Entity(cik).data.is_company` for every reporting owner, which downloads the owner's
submissions JSON from sec.gov at parse time. The XML is read with the stdlib instead, from the
same tags edgartools reads at `owners.py:126-130`.)

No network access (all sockets are blocked at import). No Snowflake. Paths to the downloaded
bronze copies are arguments.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import random
import re
import sys
import xml.etree.ElementTree as ET
from collections import Counter, defaultdict

SEED = 20260920

# Belt and braces: nothing in this script may open a socket.
import socket  # noqa: E402


def _no_network(*_a, **_k):
    raise RuntimeError("network access is disabled in 18-classify.py")


socket.socket.connect = _no_network  # type: ignore[assignment]

try:  # edgartools' own classifier, used offline on the bronze snapshot (candidate R6)
    from edgar.entity.constants import _classify_is_individual as _edgartools_is_individual  # type: ignore
except Exception:  # noqa: BLE001
    _edgartools_is_individual = None

# --------------------------------------------------------------------------------------
# Evidence extraction
# --------------------------------------------------------------------------------------

# Legal-form / entity tokens. Matched as whole words on the upper-cased, punctuation-normalised
# name. Ticket 03 item 3 lists the core set; the rest are additions seen in this corpus.
ENTITY_TOKENS = [
    "LLC", "L L C", "LP", "L P", "LLP", "LLLP", "LTD", "LIMITED", "INC", "INCORPORATED", "CORP",
    "CORPORATION", "CO", "COMPANY", "TRUST", "TRUSTS", "TR", "FUND", "FUNDS", "PARTNERS",
    "PARTNERSHIP", "HOLDINGS", "HOLDING", "CAPITAL", "MANAGEMENT", "MGMT", "FOUNDATION",
    "ESTATE", "ASSOCIATES", "GROUP", "INVESTMENTS", "INVESTMENT", "ADVISORS", "ADVISERS",
    "ADVISORY", "VENTURES", "VENTURE", "EQUITY", "EQUITIES", "GP", "SA", "S A", "NV", "N V", "BV",
    "B V", "PLC", "AG", "GMBH", "SARL", "S A R L", "PTE", "PTY", "BANK", "SECURITIES", "ASSET",
    "ASSETS", "ENTERPRISES", "INDUSTRIES", "INTERNATIONAL", "GLOBAL", "FAMILY", "LIVING",
    "REVOCABLE", "IRREVOCABLE", "FBO", "ESOP", "PLAN", "UNIVERSITY", "CHURCH", "ASSOCIATION",
    "SOCIETY", "COUNCIL", "SYSTEM", "RETIREMENT", "PENSION", "INSURANCE", "SERVICES",
    "TECHNOLOGIES", "SYSTEMS", "ENERGY", "RESOURCES", "OPPORTUNITIES", "OPPORTUNITY",
    "STRATEGIES", "MASTER", "FEEDER", "SPV", "ACQUISITION", "ACQUISITIONS", "SPONSOR",
    "SPONSORS", "CAPITAL", "PORTFOLIO", "INVESTORS", "INVESTOR", "TRUSTEE", "TRUSTEES",
    "FIDUCIARY", "NOMINEES", "NOMINEE", "SAS", "SPA", "S P A", "OY", "AB", "AS", "A S", "KG",
    "SE", "LIMITADA", "LTDA", "SDN", "BHD", "KK", "KABUSHIKI", "CAYMAN", "DELAWARE", "LIFE",
    "CREDIT", "FINANCE", "FINANCIAL", "REAL ESTATE", "REIT", "TRUST CO", "PARTNERS LP",
]
_TOKEN_RE = re.compile(
    r"(?<![A-Z0-9])(" + "|".join(re.escape(t) for t in sorted(set(ENTITY_TOKENS), key=len, reverse=True)) + r")(?![A-Z0-9])"
)
# Tokens that are also plausible surname/given-name pieces and therefore reported separately.
AMBIGUOUS_TOKENS = {"CO", "TR", "SA", "AG", "AB", "AS", "SE", "OY", "KG", "GP", "LIFE", "MASTER",
                    "GLOBAL", "ENERGY", "FAMILY", "LIVING", "SYSTEM", "CREDIT", "DELAWARE",
                    "CAYMAN", "PLAN", "CHURCH", "BANK", "EQUITY", "CAPITAL", "SPONSOR", "TRUSTEE"}

_PERSON_SUFFIX = {"JR", "SR", "II", "III", "IV", "V", "MD", "PHD", "ESQ", "CPA", "CFA", "DDS", "DR", "MR", "MRS", "MS"}

DEPUTIZATION_RE = re.compile(r"deputi[sz]", re.I)
DEPUTIZATION_BROAD_RE = re.compile(
    r"deputi[sz]|designee|designat\w+ (?:by|of|to)|representative (?:on|to) the board|"
    r"(?:right|entitled) to (?:designate|appoint|nominate)|board designee|board representative",
    re.I,
)
ENTITY_SELF_DESCRIPTION_RE = re.compile(
    r"the reporting (?:person|owner) is (?:a|an|the) (?:\w+ ){0,3}(?:limited partnership|corporation|"
    r"limited liability company|trust|fund|partnership|company|entity|general partner|"
    r"investment adviser|investment manager|managing member)\b(?!ee)",
    re.I,
)

ISSUER_FORMS = {"10-K", "10-Q", "8-K", "20-F", "40-F", "6-K", "S-1", "S-3", "S-4", "S-8", "F-1",
                "F-3", "10-K/A", "10-Q/A", "8-K/A", "20-F/A", "6-K/A", "DEF 14A", "DEFA14A",
                "424B4", "424B3", "424B5", "S-1/A", "S-3/A", "N-CEN", "N-CSR", "N-PORT", "N-2",
                "N-1A", "485BPOS", "N-Q", "N-30D", "10-12G", "10-12B", "1-A", "C", "D", "D/A",
                "REGDEX", "X-17A-5", "ARS", "11-K", "NT 10-K", "NT 10-Q", "25", "15-12G", "15-12B",
                "PRE 14A", "SC TO-I", "SC 13E3", "S-11", "S-11/A", "F-10", "F-4", "424B2", "424B1",
                "FWP", "8-A12B", "8-A12G", "CERT", "EFFECT", "CORRESP", "UPLOAD"}
INSTITUTIONAL_FORMS = {"13F-HR", "13F-HR/A", "13F-NT", "13F-NT/A", "ADV", "ADV/A", "ADV-E",
                       "N-PX", "N-PX/A", "13F-CTR", "13F-CTR/A", "NPORT-P", "NPORT-P/A", "ABS-15G",
                       "ADV-H-T", "ADV-NR", "ADV-W", "ADV-H-C", "TA-1", "TA-2", "MA", "MA-I",
                       "SBSE", "X-17A-5/A", "13H", "13H-Q", "13H-A", "13H-I", "13H-T"}
OWNERSHIP_FORMS = {"3", "3/A", "4", "4/A", "5", "5/A"}
BENEFICIAL_FORMS = {"SC 13D", "SC 13D/A", "SC 13G", "SC 13G/A", "SCHEDULE 13D", "SCHEDULE 13D/A",
                    "SCHEDULE 13G", "SCHEDULE 13G/A", "144", "144/A"}


def norm_name(name: str) -> str:
    s = name.upper()
    s = s.replace("&", " AND ")
    s = re.sub(r"[.,;:/()'\"\-]", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def entity_tokens(name: str) -> list[str]:
    n = norm_name(name)
    found = []
    for m in _TOKEN_RE.finditer(n):
        found.append(m.group(1))
    # "AND" (from &) is an entity signal on its own in EDGAR conformed names.
    if re.search(r"(?<![A-Z])AND(?![A-Z])", n) and " AND " in f" {n} ":
        found.append("&")
    return sorted(set(found))


def person_name_shape(name: str) -> bool:
    """EDGAR conformed person form: 2-5 alphabetic tokens (suffixes allowed), no digits, no '&'."""
    raw = name.strip()
    if not raw or "&" in raw or re.search(r"\d", raw):
        return False
    toks = [t for t in re.split(r"[\s,]+", norm_name(raw)) if t]
    if not (2 <= len(toks) <= 5):
        return False
    core = [t for t in toks if t not in _PERSON_SUFFIX]
    if len(core) < 2:
        return False
    return all(re.fullmatch(r"[A-Z][A-Z]*", t) for t in toks)


def parse_sgml_header(text: str) -> dict:
    """Pull every REPORTING-OWNER block (conformed name, CIK, ORGANIZATION NAME) out of the header."""
    hdr_end = text.find("</SEC-HEADER>")
    hdr = text[:hdr_end] if hdr_end > 0 else text[:20000]
    owners = {}
    for block in re.split(r"\nREPORTING-OWNER:", hdr)[1:]:
        block = block.split("\nISSUER:")[0]
        name = re.search(r"COMPANY CONFORMED NAME:[ \t]*(.*)", block)
        cik = re.search(r"CENTRAL INDEX KEY:[ \t]*(\d+)", block)
        org = re.search(r"ORGANIZATION NAME:[ \t]*(.*)", block)
        sic = re.search(r"STANDARD INDUSTRIAL CLASSIFICATION:[ \t]*(.*)", block)
        ein = re.search(r"EIN:[ \t]*(\d+)", block)
        soi = re.search(r"STATE OF INCORPORATION:[ \t]*(\S*)", block)
        fye = re.search(r"FISCAL YEAR END:[ \t]*(\d*)", block)
        if cik:
            owners[int(cik.group(1))] = {
                "header_conformed_name": (name.group(1).strip() if name else ""),
                "header_org_name": (org.group(1).strip() if org else ""),
                "header_sic": (sic.group(1).strip() if sic else ""),
                "header_ein": (ein.group(1).strip() if ein else ""),
                "header_state_of_inc": (soi.group(1).strip() if soi else ""),
                "header_fye": (fye.group(1).strip() if fye else ""),
            }
    acc = re.search(r"ACCESSION NUMBER:[ \t]*(\S+)", hdr)
    ftype = re.search(r"CONFORMED SUBMISSION TYPE:[ \t]*(\S+)", hdr)
    return {"owners": owners, "accession": acc.group(1) if acc else None,
            "header_form": ftype.group(1) if ftype else None}


def _t(el, path, default=""):
    if el is None:
        return default
    x = el.find(path)
    if x is None or x.text is None:
        return default
    return x.text.strip()


def _flag(el, path) -> bool:
    v = _t(el, path, "0").strip().lower()
    return v in ("1", "true")


def parse_artifact(path: str) -> list[dict]:
    with open(path, "rb") as f:
        raw = f.read()
    text = raw.decode("utf-8", errors="replace")
    hdr = parse_sgml_header(text)
    i = text.find("<XML>")
    j = text.rfind("</XML>")
    if i >= 0 and j >= 0:
        xml = text[i + 5 : j].strip()          # full SEC .txt submission (filing_artifact/)
    else:
        xml = text.strip()                     # bare primary document (filings/.../primary/*.xml)
        if not hdr["accession"]:
            hdr["accession"] = os.path.splitext(os.path.basename(path))[0]
    xml = re.sub(r"^<\?xml[^>]*\?>", "", xml).strip()
    try:
        root = ET.fromstring(xml)
    except ET.ParseError:
        # a few filings carry stray control characters
        xml2 = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", xml)
        root = ET.fromstring(xml2)
    if root.tag != "ownershipDocument":
        return []
    footnotes = [(fn.get("id"), (fn.text or "").strip()) for fn in root.findall("./footnotes/footnote")]
    fn_text = " ".join(t for _, t in footnotes)
    remarks = _t(root, "./remarks")
    sigs = [_t(s, "./signatureName") for s in root.findall("./ownerSignature")]
    owners_el = root.findall("./reportingOwner")
    n_nd = len(root.findall("./nonDerivativeTable/nonDerivativeTransaction"))
    n_nh = len(root.findall("./nonDerivativeTable/nonDerivativeHolding"))
    n_d = len(root.findall("./derivativeTable/derivativeTransaction"))
    n_dh = len(root.findall("./derivativeTable/derivativeHolding"))
    issuer_cik = _t(root, "./issuer/issuerCik")
    rows = []
    for idx, o in enumerate(owners_el, start=1):
        cik_raw = _t(o, "./reportingOwnerId/rptOwnerCik")
        try:
            cik = int(cik_raw) if cik_raw else None
        except ValueError:
            cik = None
        rel = o.find("./reportingOwnerRelationship")
        name = _t(o, "./reportingOwnerId/rptOwnerName")
        other_text = _t(rel, "./otherText")
        title = _t(rel, "./officerTitle")
        street1 = _t(o, "./reportingOwnerAddress/rptOwnerStreet1")
        toks = entity_tokens(name)
        h = hdr["owners"].get(cik, {}) if cik is not None else {}
        all_text = " ".join([other_text, title, fn_text, remarks])
        rows.append({
            "artifact": os.path.basename(path),
            "accession": hdr["accession"],
            "form": _t(root, "./documentType") or hdr["header_form"],
            "period": _t(root, "./periodOfReport"),
            "issuer_cik": int(issuer_cik) if issuer_cik.isdigit() else None,
            "issuer_name": _t(root, "./issuer/issuerName"),
            "owner_index": idx,
            "n_owners": len(owners_el),
            "owner_cik": cik,
            "owner_cik_raw": cik_raw,
            "owner_name": name,
            "is_director": _flag(rel, "./isDirector"),
            "is_officer": _flag(rel, "./isOfficer"),
            "is_ten_pct": _flag(rel, "./isTenPercentOwner"),
            "is_other": _flag(rel, "./isOther"),
            "officer_title": title,
            "other_text": other_text,
            "address_co": street1.upper().replace(" ", "").startswith("C/O"),
            "non_us_address": _t(o, "./reportingOwnerAddress/rptOwnerNonUSAddressFlag").lower() == "true",
            "n_nonderiv_txn": n_nd, "n_nonderiv_holding": n_nh,
            "n_deriv_txn": n_d, "n_deriv_holding": n_dh,
            "n_footnotes": len(footnotes),
            "deputization_strict": bool(DEPUTIZATION_RE.search(all_text)),
            "deputization_broad": bool(DEPUTIZATION_BROAD_RE.search(all_text)),
            "deputization_snippet": _snippet(all_text, DEPUTIZATION_BROAD_RE),
            "entity_self_description": _snippet(all_text, ENTITY_SELF_DESCRIPTION_RE),
            "signature_names": sigs,
            "signature_by": any(re.search(r"\bby\b|its\b|general partner|managing member|attorney", s, re.I) for s in sigs),
            "entity_tokens": toks,
            "has_entity_token": bool(toks),
            "has_unambiguous_token": bool(set(toks) - AMBIGUOUS_TOKENS),
            "person_name_shape": person_name_shape(name),
            **h,
        })
    return rows


def _snippet(text: str, rx: re.Pattern, width: int = 160) -> str:
    m = rx.search(text)
    if not m:
        return ""
    a = max(0, m.start() - width // 2)
    return text[a : m.end() + width // 2].strip()


def flag_combo(r: dict) -> str:
    parts = []
    if r["is_officer"]:
        parts.append("officer")
    if r["is_director"]:
        parts.append("director")
    if r["is_ten_pct"]:
        parts.append("10pct")
    if r["is_other"]:
        parts.append("other")
    return "+".join(parts) if parts else "none"


def load_submission(sub_dir: str, cik: int) -> dict | None:
    p = os.path.join(sub_dir, f"{cik}.json")
    if not os.path.exists(p):
        return None
    with open(p) as f:
        d = json.load(f)
    forms = d.get("filings", {}).get("recent", {}).get("form", []) or []
    fc = Counter(forms)
    non_own = {f for f in fc if f not in OWNERSHIP_FORMS}
    return {
        "sub_present": True,
        "sub_name": d.get("name") or "",
        "entity_type": d.get("entityType") or "",
        "sic": str(d.get("sic") or ""),
        "sic_description": d.get("sicDescription") or "",
        "owner_org": d.get("ownerOrg") or "",
        "ein": str(d.get("ein") or ""),
        "state_of_incorporation": d.get("stateOfIncorporation") or "",
        "category": d.get("category") or "",
        "fiscal_year_end": d.get("fiscalYearEnd") or "",
        "n_tickers": len(d.get("tickers") or []),
        "tickers": list(d.get("tickers") or []),
        "exchanges": [x for x in (d.get("exchanges") or []) if x],
        "forms_first50": forms[:50],
        "n_former_names": len(d.get("formerNames") or []),
        "former_names": [x.get("name") for x in (d.get("formerNames") or [])][:5],
        "insider_txn_for_owner": d.get("insiderTransactionForOwnerExists"),
        "insider_txn_for_issuer": d.get("insiderTransactionForIssuerExists"),
        "n_recent_filings": len(forms),
        "n_form_kinds": len(fc),
        "forms_top": fc.most_common(8),
        "non_ownership_forms": sorted(non_own),
        "only_ownership_forms": len(forms) > 0 and not non_own,
        "has_issuer_forms": bool(non_own & ISSUER_FORMS),
        "has_institutional_forms": bool(non_own & INSTITUTIONAL_FORMS),
        "has_beneficial_forms": bool(non_own & BENEFICIAL_FORMS),
        "has_other_forms": bool(non_own - ISSUER_FORMS - INSTITUTIONAL_FORMS - BENEFICIAL_FORMS),
        "other_forms": sorted(non_own - ISSUER_FORMS - INSTITUTIONAL_FORMS - BENEFICIAL_FORMS)[:10],
        "business_state": (d.get("addresses") or {}).get("business", {}).get("stateOrCountry") or "",
        "mailing_street": (d.get("addresses") or {}).get("mailing", {}).get("street1") or "",
    }


def stage_parse(args):
    files = sorted(os.listdir(args.artifacts))
    rows = []
    bad = []
    for k, fn in enumerate(files):
        try:
            rows.extend(parse_artifact(os.path.join(args.artifacts, fn)))
        except Exception as e:  # noqa: BLE001
            bad.append((fn, repr(e)))
        if (k + 1) % 1000 == 0:
            print(f"parsed {k+1}/{len(files)}", file=sys.stderr)
    subs_cache = {}
    for r in rows:
        r["flag_combo"] = flag_combo(r)
        cik = r["owner_cik"]
        if cik is None:
            r.update({"sub_present": False})
            continue
        if cik not in subs_cache:
            subs_cache[cik] = load_submission(args.submissions, cik)
        s = subs_cache[cik]
        if s is None:
            r.update({"sub_present": False})
        else:
            r.update(s)
    with open(args.out, "w") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    print(f"rows={len(rows)} files={len(files)} bad={len(bad)}", file=sys.stderr)
    for b in bad:
        print("BAD", b, file=sys.stderr)
# --------------------------------------------------------------------------------------
# Sampling
# --------------------------------------------------------------------------------------

def owner_key(r: dict) -> str:
    return str(r["owner_cik"]) if r["owner_cik"] is not None else f"name:{norm_name(r['owner_name'])}"


def stratum(r: dict) -> str:
    return f"{r['flag_combo']}|{'token' if r['has_entity_token'] else 'notoken'}"


def draft_label(r: dict) -> tuple[str, str, str]:
    """Draft label for the human pass. Name reading is primary (that is what a human does);
    structural evidence from the owner CIK's submissions.json is used only where it is strong
    (tickers/exchanges, issuer forms such as 10-K/8-K/S-1/N-CEN, 13F-HR or ADV, an EIN) and any
    conflict between the two is left 'unsure' for the human to decide. entityType, the four
    relationship flags and the ticket-03 token list are deliberately NOT decisive here: they are
    candidate rules. Returns (label, evidence_class, reason)."""
    reasons = []
    strong_entity = False
    if r.get("sub_present"):
        if r.get("n_tickers") or r.get("exchanges"):
            strong_entity = True; reasons.append("tickers/exchanges")
        if r.get("has_issuer_forms"):
            strong_entity = True; reasons.append("issuer forms " + ",".join(sorted(set(r["non_ownership_forms"]) & ISSUER_FORMS)[:4]))
        inst = sorted((set(r.get("non_ownership_forms") or []) & INSTITUTIONAL_FORMS) - {"13F-NT", "13F-NT/A"})
        if inst:
            strong_entity = True; reasons.append("institutional forms " + ",".join(inst[:4]))
        if r.get("ein"):
            strong_entity = True; reasons.append("EIN present")
        for f, lab in (("state_of_incorporation", "soi"), ("fiscal_year_end", "fye"), ("sic", "sic"), ("owner_org", "org")):
            if r.get(f):
                reasons.append(f"{lab}={r[f]} (weak)")
    if r.get("header_org_name"):
        reasons.append(f"header org={r['header_org_name']} (weak)")
    if r.get("entity_self_description"):
        reasons.append("text: " + r["entity_self_description"][:80])
    if r.get("signature_by"):
        reasons.append("signed 'by/its' " + "; ".join(r["signature_names"])[:60])
    name_entity = r["has_unambiguous_token"]
    name_person = r["person_name_shape"] and not r["has_entity_token"]
    if name_entity and not strong_entity:
        return "entity", "name", "entity token(s) " + ",".join(r["entity_tokens"]) + ("; " + "; ".join(reasons) if reasons else "")
    if name_entity and strong_entity:
        return "entity", "name+structural", "entity token(s) " + ",".join(r["entity_tokens"]) + "; " + "; ".join(reasons)
    if name_person and not strong_entity:
        return "person", "name", "person-form name; " + ("; ".join(reasons) if reasons else "no strong structural field")
    return "unsure", "conflict" if (name_person and strong_entity) else "none", "; ".join(reasons) or "name shape unclear, no structural field"


def stage_sample(args):
    rows = [json.loads(l) for l in open(args.owners)]
    # one representative row per distinct owner (deterministic: first accession in sorted order)
    by_owner = defaultdict(list)
    for r in rows:
        by_owner[owner_key(r)].append(r)
    owners = {}
    for k, rs in by_owner.items():
        rs = sorted(rs, key=lambda r: (r["accession"], r["owner_index"]))
        rep = dict(rs[0])
        rep["n_rows"] = len(rs)
        rep["flag_combos_seen"] = sorted({flag_combo(x) for x in rs})
        rep["any_deputization_broad"] = any(x["deputization_broad"] for x in rs)
        rep["any_entity_self_description"] = next((x["entity_self_description"] for x in rs if x["entity_self_description"]), "")
        rep["any_signature_by"] = any(x["signature_by"] for x in rs)
        owners[k] = rep
    cells = defaultdict(list)
    for k, rep in owners.items():
        cells[stratum(rep)].append(k)
    rng = random.Random(SEED)
    sample = []
    plan = {}
    for cell in sorted(cells):
        keys = sorted(cells[cell])
        cap = args.rare_cap if len(keys) <= args.rare_threshold else args.cap
        # if the cell is the big person-looking cell, take the larger cap
        if cell in ("officer|notoken", "director|notoken", "officer+director|notoken"):
            cap = args.big_cap
        if cell in (args.full_cells or "").split(","):
            cap = len(keys)
        take = keys if len(keys) <= cap else rng.sample(keys, cap)
        plan[cell] = {"population_owners": len(keys), "sampled": len(take)}
        for k in take:
            rep = owners[k]
            lab, cls, why = draft_label(rep)
            sample.append({
                "owner_key": k, "stratum": cell, "draft_label": lab, "draft_evidence_class": cls,
                "draft_reason": why, "label": None, "label_reason": None, "uncertain": False,
                **{f: rep.get(f) for f in (
                    "owner_cik", "owner_name", "sub_name", "flag_combo", "flag_combos_seen", "officer_title",
                    "other_text", "entity_tokens", "person_name_shape", "entity_type", "sic",
                    "sic_description", "owner_org", "ein", "state_of_incorporation", "n_tickers",
                    "n_former_names", "former_names", "fiscal_year_end", "forms_top", "non_ownership_forms",
                    "only_ownership_forms", "n_recent_filings", "header_org_name", "header_conformed_name",
                    "address_co", "non_us_address", "signature_names", "any_signature_by",
                    "any_deputization_broad", "deputization_snippet", "any_entity_self_description",
                    "accession", "issuer_name", "n_rows", "sub_present")},
            })
    with open(args.out, "w") as f:
        for s in sample:
            f.write(json.dumps(s, ensure_ascii=False) + "\n")
    with open(args.plan_out, "w") as f:
        json.dump(plan, f, indent=1)
    print(json.dumps(plan, indent=1), file=sys.stderr)
    print(f"sampled owners={len(sample)} distinct owners={len(owners)}", file=sys.stderr)


# --------------------------------------------------------------------------------------
# Candidate rules
# --------------------------------------------------------------------------------------

def _empty(v) -> bool:
    return v in (None, "", 0, [], {})


def _structural_empty(r: dict) -> bool:
    return (_empty(r.get("sic")) and _empty(r.get("state_of_incorporation")) and _empty(r.get("ein"))
            and _empty(r.get("n_tickers")) and _empty(r.get("owner_org")) and _empty(r.get("fiscal_year_end")))


def rule_entity_type(r):            # R1: ticket 03 item 1 as proposed
    et = r.get("entity_type")
    if not r.get("sub_present"):
        return "deferred"
    if et in ("operating", "investment"):
        return "entity"
    if et == "other":
        return "person"
    return "deferred"


def rule_entity_type_defer_other(r):  # R1b: other -> deferred
    et = r.get("entity_type")
    if not r.get("sub_present"):
        return "deferred"
    if et in ("operating", "investment"):
        return "entity"
    return "deferred"


def rule_flags(r):                  # R2: officer/director -> person; 10%-only / other-only -> entity
    if r["is_officer"] or r["is_director"]:
        return "person"
    if r["is_ten_pct"] or r["is_other"]:
        return "entity"
    return "deferred"


def rule_flags_defer_rest(r):       # R2b: officer/director -> person; anything else deferred
    if r["is_officer"] or r["is_director"]:
        return "person"
    return "deferred"


def rule_name_tokens(r):            # R3: token -> entity; person-shaped no-token name -> person
    if r["has_entity_token"]:
        return "entity"
    if r["person_name_shape"]:
        return "person"
    return "deferred"


def rule_name_tokens_strict(r):     # R3b: unambiguous token -> entity; person shape & no token at all -> person
    if r["has_unambiguous_token"]:
        return "entity"
    if r["has_entity_token"]:
        return "deferred"
    if r["person_name_shape"]:
        return "person"
    return "deferred"


def rule_structural(r):             # R4: submissions structural fields (advisor's first-class candidate)
    if not r.get("sub_present"):
        return "deferred"
    if r.get("entity_type") in ("operating", "investment"):
        return "entity"
    if not _structural_empty(r):
        return "entity"
    return "person"


def rule_structural_defer_tokens(r):  # R4b: structural person only when the name carries no token
    v = rule_structural(r)
    if v == "person" and r["has_entity_token"]:
        return "deferred"
    return v


def rule_form_history(r):           # R5: filing-form history of the owner CIK
    if not r.get("sub_present"):
        return "deferred"
    if r.get("has_issuer_forms") or r.get("has_institutional_forms"):
        return "entity"
    if r.get("only_ownership_forms"):
        return "person"
    return "deferred"


def rule_combo_a(r):
    """C-A: person iff officer/director AND no entity token AND structural-empty submissions;
    entity iff entityType operating/investment OR structural field present OR unambiguous token;
    else deferred."""
    if not r.get("sub_present"):
        return "deferred"
    ent = (r.get("entity_type") in ("operating", "investment")) or (not _structural_empty(r)) or r["has_unambiguous_token"]
    per = (r["is_officer"] or r["is_director"]) and not r["has_entity_token"] and _structural_empty(r) and r["person_name_shape"]
    if ent and not per:
        return "entity"
    if per and not ent:
        return "person"
    return "deferred"


def rule_combo_b(r):
    """C-B: like C-A but a 10%-only / other-only row can also be person when structural-empty and
    person-shaped (i.e. flags are not required for person)."""
    if not r.get("sub_present"):
        return "deferred"
    ent = (r.get("entity_type") in ("operating", "investment")) or (not _structural_empty(r)) or r["has_unambiguous_token"]
    per = (not r["has_entity_token"]) and _structural_empty(r) and r["person_name_shape"]
    if ent and not per:
        return "entity"
    if per and not ent:
        return "person"
    return "deferred"


def rule_combo_c(r):
    """C-C: C-B plus deputization guard: a director/officer row whose filing text mentions
    deputization/designee is deferred rather than person."""
    v = rule_combo_b(r)
    if v == "person" and r.get("deputization_broad"):
        return "deferred"
    return v


def rule_combo_d(r):
    """C-D: C-B plus form-history guard: person only when the owner CIK has filed only 3/4/5
    (or SC 13D/G / 144, which individuals also file); entity additionally when the CIK files
    issuer/institutional forms."""
    if not r.get("sub_present"):
        return "deferred"
    v = rule_combo_b(r)
    if r.get("has_issuer_forms") or r.get("has_institutional_forms"):
        return "entity" if v != "person" else "deferred"
    if v == "person" and r.get("has_other_forms"):
        return "deferred"
    return v


def rule_combo_e(r):
    """C-E: C-D restricted to officer/director rows for person (10%-only / other-only never auto-person)."""
    v = rule_combo_d(r)
    if v == "person" and not (r["is_officer"] or r["is_director"]):
        return "deferred"
    return v


def rule_edgartools(r):             # R6: edgartools 5.58.0 `_classify_is_individual` on the bronze snapshot
    if not r.get("sub_present") or _edgartools_is_individual is None:
        return "deferred"
    ind = _edgartools_is_individual(
        name=r.get("sub_name"), tickers=r.get("tickers"), exchanges=r.get("exchanges"),
        state_of_incorporation=r.get("state_of_incorporation"), entity_type=r.get("entity_type"),
        forms=r.get("forms_first50"), ein=r.get("ein"), cik=r.get("owner_cik"),
        insider_transaction_for_issuer_exists=bool(r.get("insider_txn_for_issuer")),
        insider_transaction_for_owner_exists=bool(r.get("insider_txn_for_owner")),
    )
    return "person" if ind else "entity"


def rule_combo_f(r):
    """C-F: edgartools chain, but auto-person only when this file's independent checks agree
    (person-shaped name, no entity token by the ticket-03 list, structural-empty, no
    deputization text); every disagreement is deferred."""
    v = rule_edgartools(r)
    if v == "person":
        if r["has_entity_token"] or not r["person_name_shape"] or not _structural_empty(r) or r.get("deputization_broad"):
            return "deferred"
    return v


def rule_combo_g(r):
    """C-G: C-F restricted to officer/director rows for auto-person."""
    v = rule_combo_f(r)
    if v == "person" and not (r["is_officer"] or r["is_director"]):
        return "deferred"
    return v


SURNAME_PLAUSIBLE_TOKENS = AMBIGUOUS_TOKENS | {"TRUST"}


def rule_combo_h(r):
    """C-H (advisor-suggested best-of-both): person iff no entity token AND structural-empty AND
    person-shaped (C-B's person clause); entity iff entityType operating/investment OR an
    unambiguous name token -- WITHOUT the 'structural field present' clause, because SEC populates
    stateOfIncorporation/FYE/SIC on a minority of genuine person CIKs; else deferred."""
    if not r.get("sub_present"):
        return "deferred"
    if r.get("entity_type") in ("operating", "investment") or r["has_unambiguous_token"]:
        return "entity"
    if (not r["has_entity_token"]) and _structural_empty(r) and r["person_name_shape"]:
        return "person"
    return "deferred"


def rule_combo_i(r):
    """C-I: C-H plus a surname-token guard: a two-word, structural-empty name whose only token is
    surname-plausible (e.g. 'Trust Jane') is deferred instead of auto-entity. Post-hoc: added after
    'Trust Jane' was the sole entity-side error; its deferral cost is measured on the population."""
    v = rule_combo_h(r)
    if v == "entity" and r.get("entity_type") not in ("operating", "investment"):
        words = [w for w in norm_name(r["owner_name"]).split() if w]
        if len(words) == 2 and _structural_empty(r) and set(r["entity_tokens"]) <= SURNAME_PLAUSIBLE_TOKENS:
            return "deferred"
    return v


def rule_combo_j(r):
    """C-J: C-H plus a general surname-token guard: a token-bearing name that is otherwise
    person-shaped (2-5 alphabetic words, no '&'/digits), structurally empty in submissions.json and
    carries exactly ONE entity token is deferred instead of auto-entity. Post-hoc after two such
    persons were found ('Trust Jane', 'Council LaVerne H'); no token list is consulted."""
    v = rule_combo_h(r)
    if v == "entity" and r.get("entity_type") not in ("operating", "investment"):
        if r["person_name_shape"] and _structural_empty(r) and len(r["entity_tokens"]) == 1:
            return "deferred"
    return v


RULES = {
    "R1 entityType (other->person)": rule_entity_type,
    "R1b entityType (other->deferred)": rule_entity_type_defer_other,
    "R2 flags (off/dir->person, 10%/other->entity)": rule_flags,
    "R2b flags (off/dir->person, rest deferred)": rule_flags_defer_rest,
    "R3 name tokens (token->entity, person-shape->person)": rule_name_tokens,
    "R3b name tokens strict (ambiguous token->deferred)": rule_name_tokens_strict,
    "R4 submissions structural-empty (other & no sic/state/ein/ticker/org/fye -> person)": rule_structural,
    "R4b structural-empty, token->deferred": rule_structural_defer_tokens,
    "R5 form history (only 3/4/5 -> person; issuer/institutional forms -> entity)": rule_form_history,
    "C-A off/dir & no token & structural-empty -> person; struct/token -> entity": rule_combo_a,
    "C-B no token & structural-empty & person-shape -> person (flags not required)": rule_combo_b,
    "C-C C-B + deputization text -> deferred": rule_combo_c,
    "C-D C-B + form-history guard": rule_combo_d,
    "C-E C-D, person only for off/dir rows": rule_combo_e,
    "R6 edgartools 5.58.0 _classify_is_individual (offline on bronze submissions)": rule_edgartools,
    "C-F edgartools person & name/structural/deputization checks agree, else deferred": rule_combo_f,
    "C-G C-F, person only for off/dir rows": rule_combo_g,
    "C-H person: no token & structural-empty & person-shape; entity: entityType op/inv OR unambiguous token": rule_combo_h,
    "C-I C-H + two-word surname-token names deferred": rule_combo_i,
    "C-J C-H + single-token person-shaped structural-empty names deferred": rule_combo_j,
}


# --------------------------------------------------------------------------------------
# Scoring
# --------------------------------------------------------------------------------------

def wilson(k: int, n: int, z: float = 1.959964) -> tuple[float, float, float]:
    if n == 0:
        return (float("nan"), float("nan"), float("nan"))
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (p, c - h, c + h)


def n_for_lcb(target: float = 0.99, z: float = 1.959964) -> int:
    """Smallest n such that the Wilson lower bound with zero errors reaches `target`: n/(n+z^2) >= target."""
    return math.ceil(target * z * z / (1 - target))


def stage_score(args):
    rows = [json.loads(l) for l in open(args.owners)]
    sample = [json.loads(l) for l in open(args.sample)]
    labeled = [s for s in sample if s.get("label") in ("person", "entity")]
    uncertain = [s for s in sample if s.get("uncertain")]
    # population weights per stratum (owner-level)
    by_owner = {}
    for r in rows:
        k = owner_key(r)
        if k not in by_owner:
            by_owner[k] = r
    pop_cells = Counter(stratum(r) for r in by_owner.values())
    samp_cells = Counter(s["stratum"] for s in labeled)
    weight = {c: pop_cells[c] / samp_cells[c] for c in samp_cells}
    # the sample rows carry the representative-row evidence; rebuild the full evidence row
    rep_rows = {owner_key(r): r for r in rows}  # first occurrence == representative (sorted parse order)
    for r in rows:  # ensure representative == the one used in sampling (accession-sorted first)
        k = owner_key(r)
        cur = rep_rows[k]
        if (r["accession"], r["owner_index"]) < (cur["accession"], cur["owner_index"]):
            rep_rows[k] = r
    out = {"n_rows": len(rows), "n_distinct_owners": len(by_owner), "n_labeled": len(labeled),
           "n_uncertain": len(uncertain), "wilson_n_for_99_lcb_zero_errors": n_for_lcb(),
           "population_cells_owners": dict(sorted(pop_cells.items())),
           "sample_cells": dict(sorted(samp_cells.items())), "rules": {}}
    label_by_key = {s["owner_key"]: s for s in labeled}
    for rname, fn in RULES.items():
        rec = {"decided_person": 0, "person_correct": 0, "decided_entity": 0, "entity_correct": 0,
               "deferred": 0, "w_person": 0.0, "w_person_correct": 0.0, "w_entity": 0.0,
               "w_entity_correct": 0.0, "w_deferred": 0.0, "errors": [], "per_cell": {}}
        for s in labeled:
            r = rep_rows[s["owner_key"]]
            v = fn(r)
            w = weight[s["stratum"]]
            cell = rec["per_cell"].setdefault(s["stratum"], Counter())
            cell[v] += 1
            if v == "person":
                rec["decided_person"] += 1; rec["w_person"] += w
                if s["label"] == "person":
                    rec["person_correct"] += 1; rec["w_person_correct"] += w
                else:
                    rec["errors"].append({"key": s["owner_key"], "name": s["owner_name"], "decided": v, "label": s["label"], "reason": s["label_reason"]})
                    cell["person_wrong"] += 1
            elif v == "entity":
                rec["decided_entity"] += 1; rec["w_entity"] += w
                if s["label"] == "entity":
                    rec["entity_correct"] += 1; rec["w_entity_correct"] += w
                else:
                    rec["errors"].append({"key": s["owner_key"], "name": s["owner_name"], "decided": v, "label": s["label"], "reason": s["label_reason"]})
                    cell["entity_wrong"] += 1
            else:
                rec["deferred"] += 1; rec["w_deferred"] += w
        p, lo, hi = wilson(rec["person_correct"], rec["decided_person"])
        rec["person_precision"] = p; rec["person_wilson95"] = [lo, hi]
        p, lo, hi = wilson(rec["entity_correct"], rec["decided_entity"])
        rec["entity_precision"] = p; rec["entity_wilson95"] = [lo, hi]
        rec["person_precision_weighted"] = rec["w_person_correct"] / rec["w_person"] if rec["w_person"] else None
        rec["entity_precision_weighted"] = rec["w_entity_correct"] / rec["w_entity"] if rec["w_entity"] else None
        rec["deferral_share_sample"] = rec["deferred"] / len(labeled)
        # population deferral share, rows and owners, applying the rule to every row / owner
        dec_rows = Counter(fn(r) for r in rows)
        dec_own = Counter(fn(r) for r in rep_rows.values())
        rec["population_rows"] = dict(dec_rows)
        rec["population_owners"] = dict(dec_own)
        rec["deferral_share_rows"] = dec_rows["deferred"] / len(rows)
        rec["deferral_share_owners"] = dec_own["deferred"] / len(rep_rows)
        rec["per_cell"] = {c: dict(v) for c, v in sorted(rec["per_cell"].items())}
        rec["clears_99_lcb_person"] = rec["person_wilson95"][0] >= 0.99 if rec["decided_person"] else False
        rec["clears_99_lcb_entity"] = rec["entity_wilson95"][0] >= 0.99 if rec["decided_entity"] else False
        out["rules"][rname] = rec
    # descriptive stats over all rows
    out["flag_combo_rows"] = dict(Counter(r["flag_combo"] for r in rows).most_common())
    out["flag_combo_owners"] = dict(Counter(r["flag_combo"] for r in rep_rows.values()).most_common())
    out["multi_owner_rows"] = sum(1 for r in rows if r["n_owners"] > 1)
    out["multi_owner_filings"] = len({r["accession"] for r in rows if r["n_owners"] > 1})
    out["filings"] = len({r["accession"] for r in rows})
    out["forms"] = dict(Counter(r["form"] for r in rows))
    out["owner_cik_missing_rows"] = sum(1 for r in rows if r["owner_cik"] is None)
    out["sub_missing_rows"] = sum(1 for r in rows if r["owner_cik"] is not None and not r.get("sub_present"))
    out["sub_missing_owners"] = sum(1 for r in rep_rows.values() if r["owner_cik"] is not None and not r.get("sub_present"))
    out["entity_type_rows"] = dict(Counter(r.get("entity_type", "<no submissions>") or "<blank>" for r in rows))
    out["entity_type_owners"] = dict(Counter(r.get("entity_type", "<no submissions>") or "<blank>" for r in rep_rows.values()))
    out["entity_type_by_flag_combo_rows"] = {
        c: dict(Counter((r.get("entity_type") or "<blank>") for r in rows if r["flag_combo"] == c))
        for c in out["flag_combo_rows"]}
    out["token_by_flag_combo_rows"] = {
        c: dict(Counter("token" if r["has_entity_token"] else "notoken" for r in rows if r["flag_combo"] == c))
        for c in out["flag_combo_rows"]}
    out["deputization_strict_rows"] = sum(1 for r in rows if r["deputization_strict"])
    out["deputization_broad_rows"] = sum(1 for r in rows if r["deputization_broad"])
    out["deputization_strict_filings"] = len({r["accession"] for r in rows if r["deputization_strict"]})
    out["deputization_strict_by_flag_combo"] = dict(Counter(r["flag_combo"] for r in rows if r["deputization_strict"]))
    out["deputization_strict_owners"] = sorted({(r["owner_cik"], r["owner_name"]) for r in rows if r["deputization_strict"]})
    out["other_text_rows"] = sum(1 for r in rows if r["other_text"])
    out["other_text_top"] = Counter(r["other_text"] for r in rows if r["other_text"]).most_common(25)
    out["entity_self_description_rows"] = sum(1 for r in rows if r["entity_self_description"])
    out["structural_empty_by_entity_type_owners"] = {
        et: dict(Counter("empty" if _structural_empty(r) else "populated" for r in rep_rows.values() if (r.get("entity_type") or "<blank>") == et))
        for et in out["entity_type_owners"]}
    out["header_org_rows"] = sum(1 for r in rows if r.get("header_org_name"))
    out["labels"] = dict(Counter(s["label"] for s in labeled))
    out["labels_by_cell"] = {c: dict(Counter(s["label"] for s in labeled if s["stratum"] == c)) for c in sorted(samp_cells)}
    out["label_evidence_class"] = dict(Counter(s.get("label_evidence_class") or s.get("draft_evidence_class") for s in labeled))
    out["draft_overrides"] = [{"key": s["owner_key"], "name": s["owner_name"], "draft": s["draft_label"], "label": s["label"], "reason": s["label_reason"]}
                              for s in labeled if s["draft_label"] != s["label"]]
    out["uncertain_cases"] = [{"key": s["owner_key"], "name": s["owner_name"], "stratum": s["stratum"], "label": s["label"], "reason": s["label_reason"]} for s in uncertain]
    # hashes last
    out["sha256"] = {os.path.basename(p): _sha(p) for p in (args.owners, args.sample)}
    with open(args.out, "w") as f:
        json.dump(out, f, indent=1, ensure_ascii=False, default=str)
    _print_table(out)


def _sha(p: str) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _print_table(out: dict):
    print(f"rows={out['n_rows']} owners={out['n_distinct_owners']} labeled={out['n_labeled']} n_for_99lcb={out['wilson_n_for_99_lcb_zero_errors']}")
    print(f"{'rule':<78} {'P n':>5} {'P prec':>7} {'P lcb':>6} {'E n':>5} {'E prec':>7} {'E lcb':>6} {'defer rows':>10} {'defer own':>9}")
    for rname, rec in out["rules"].items():
        pp = rec["person_precision"]; pl = rec["person_wilson95"][0]
        ep = rec["entity_precision"]; el = rec["entity_wilson95"][0]
        print(f"{rname[:78]:<78} {rec['decided_person']:>5} {pp:>7.4f} {pl:>6.4f} {rec['decided_entity']:>5} {ep:>7.4f} {el:>6.4f} {rec['deferral_share_rows']:>10.4f} {rec['deferral_share_owners']:>9.4f}")


# --------------------------------------------------------------------------------------
# Entity-arm extension from the legacy-path corpus (filings/sec/cik=*/accession=*/primary/*.xml)
# --------------------------------------------------------------------------------------

def stage_extend(args):
    """Parse the bare primary XMLs of the legacy fetch path, report the flag/token distribution of
    that corpus, and draw a deterministic sample of token-bearing owners NOT present in the primary
    corpus (entity-arm supplement only; the person arm is never re-drawn over the union)."""
    primary_keys = set()
    for l in open(args.primary_owners):
        primary_keys.add(owner_key(json.loads(l)))
    files = sorted(os.listdir(args.artifacts))
    rows, bad, non_own = [], [], 0
    for k, fn in enumerate(files):
        try:
            rs = parse_artifact(os.path.join(args.artifacts, fn))
        except Exception as e:  # noqa: BLE001
            bad.append((fn, repr(e)[:80])); continue
        if not rs:
            non_own += 1; continue
        for r in rs:
            r["flag_combo"] = flag_combo(r)
        rows.extend(rs)
        if (k + 1) % 20000 == 0:
            print(f"parsed {k+1}/{len(files)}", file=sys.stderr)
    by_owner = {}
    for r in rows:
        by_owner.setdefault(owner_key(r), r)
    stats = {
        "files": len(files), "ownership_files": len(files) - non_own - len(bad), "non_ownership_files": non_own,
        "bad_files": len(bad), "rows": len(rows), "distinct_owners": len(by_owner),
        "forms": dict(Counter(r["form"] for r in rows).most_common()),
        "flag_combo_rows": dict(Counter(r["flag_combo"] for r in rows).most_common()),
        "token_by_flag_combo_rows": {c: dict(Counter("token" if r["has_entity_token"] else "notoken" for r in rows if r["flag_combo"] == c))
                                     for c in Counter(r["flag_combo"] for r in rows)},
        "multi_owner_rows": sum(1 for r in rows if r["n_owners"] > 1),
        "owner_cik_missing_rows": sum(1 for r in rows if r["owner_cik"] is None),
        "deputization_strict_rows": sum(1 for r in rows if r["deputization_strict"]),
        "period_min": min((r["period"] for r in rows if r["period"]), default=None),
        "period_max": max((r["period"] for r in rows if r["period"]), default=None),
        "owners_also_in_primary": sum(1 for k in by_owner if k in primary_keys),
        "token_owners": sum(1 for r in by_owner.values() if r["has_entity_token"]),
        "token_owners_not_in_primary": sum(1 for k, r in by_owner.items() if r["has_entity_token"] and k not in primary_keys),
    }
    sub_ciks = set(l.strip() for l in open(args.submissions_cik_list)) if args.submissions_cik_list else None
    cands = sorted(k for k, r in by_owner.items() if r["has_entity_token"] and k not in primary_keys
                   and r["owner_cik"] is not None and (sub_ciks is None or str(r["owner_cik"]) in sub_ciks))
    stats["token_owners_not_in_primary_with_bronze_submissions"] = len(cands)
    rng = random.Random(SEED)
    take = cands if len(cands) <= args.n else rng.sample(cands, args.n)
    with open(args.out_rows, "w") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    with open(args.out_sample, "w") as f:
        for k in sorted(take):
            f.write(json.dumps(by_owner[k], ensure_ascii=False) + "\n")
    with open(args.out_stats, "w") as f:
        json.dump(stats, f, indent=1)
    print(json.dumps(stats, indent=1), file=sys.stderr)


def stage_score_extension(args):
    """Score the entity-side decision of every rule on the labeled extension sample, alone and
    pooled with the primary sample's entity-decided owners."""
    ext = [json.loads(l) for l in open(args.sample)]
    prim = json.load(open(args.primary_summary))
    out = {"n_extension_labeled": len(ext), "labels": dict(Counter(s["label"] for s in ext)), "rules": {}}
    subs_cache = {}
    for s in ext:
        cik = s["owner_cik"]
        if cik not in subs_cache:
            subs_cache[cik] = load_submission(args.submissions, cik)
        s.update(subs_cache[cik] or {"sub_present": False})
    for rname, fn in RULES.items():
        dec = Counter(); errs = []
        for s in ext:
            v = fn(s)
            dec[v] += 1
            if v in ("person", "entity") and v != s["label"]:
                errs.append({"key": owner_key(s), "name": s["owner_name"], "decided": v, "label": s["label"], "reason": s["label_reason"]})
                dec[v + "_wrong"] += 1
        e_n, e_ok = dec["entity"], dec["entity"] - dec["entity_wrong"]
        p, lo, hi = wilson(e_ok, e_n)
        pr = prim["rules"][rname]
        pn, pok = pr["decided_entity"], pr["entity_correct"]
        pp, plo, phi = wilson(pok + e_ok, pn + e_n)
        out["rules"][rname] = {"extension_decisions": dict(dec), "extension_entity_precision": p, "extension_entity_wilson95": [lo, hi],
                               "pooled_decided_entity": pn + e_n, "pooled_entity_correct": pok + e_ok,
                               "pooled_entity_precision": pp, "pooled_entity_wilson95": [plo, phi],
                               "pooled_clears_99_lcb_entity": plo >= 0.99 if (pn + e_n) else False, "errors": errs}
    out["sha256"] = {os.path.basename(args.sample): _sha(args.sample)}
    with open(args.out, "w") as f:
        json.dump(out, f, indent=1, ensure_ascii=False, default=str)
    print(f"{'rule':<78} {'ext E n':>7} {'ext prec':>8} {'pooled n':>8} {'pooled prec':>11} {'pooled lcb':>10}")
    for rname, rec in out["rules"].items():
        print(f"{rname[:78]:<78} {rec['extension_decisions'].get('entity',0):>7} {rec['extension_entity_precision']:>8.4f} {rec['pooled_decided_entity']:>8} {rec['pooled_entity_precision']:>11.4f} {rec['pooled_entity_wilson95'][0]:>10.4f}")


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="stage", required=True)
    p = sub.add_parser("parse")
    p.add_argument("--artifacts", required=True)
    p.add_argument("--submissions", required=True)
    p.add_argument("--out", required=True)
    p.set_defaults(fn=stage_parse)
    s = sub.add_parser("sample")
    s.add_argument("--owners", required=True)
    s.add_argument("--out", required=True)
    s.add_argument("--plan-out", required=True)
    s.add_argument("--cap", type=int, default=60)
    s.add_argument("--big-cap", type=int, default=150)
    s.add_argument("--rare-threshold", type=int, default=40)
    s.add_argument("--rare-cap", type=int, default=40)
    s.add_argument("--full-cells", default="", help="comma-separated strata to take in full")
    s.set_defaults(fn=stage_sample)
    c = sub.add_parser("score")
    c.add_argument("--owners", required=True)
    c.add_argument("--sample", required=True)
    c.add_argument("--out", required=True)
    c.set_defaults(fn=stage_score)
    e = sub.add_parser("extend")
    e.add_argument("--artifacts", required=True, help="directory of bare primary XMLs (legacy path)")
    e.add_argument("--primary-owners", required=True, help="18-owners.jsonl of the primary corpus")
    e.add_argument("--submissions-cik-list", default=None, help="file with one CIK per line that bronze holds a submissions.json for")
    e.add_argument("--n", type=int, default=160)
    e.add_argument("--out-rows", required=True)
    e.add_argument("--out-sample", required=True)
    e.add_argument("--out-stats", required=True)
    e.set_defaults(fn=stage_extend)
    x = sub.add_parser("score-extension")
    x.add_argument("--sample", required=True, help="labeled extension sample JSONL")
    x.add_argument("--submissions", required=True)
    x.add_argument("--primary-summary", required=True)
    x.add_argument("--out", required=True)
    x.set_defaults(fn=stage_score_extension)
    args = ap.parse_args()
    args.fn(args)


if __name__ == "__main__":
    main()
