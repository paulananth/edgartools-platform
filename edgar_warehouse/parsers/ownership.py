"""Ownership parser for Forms 3, 4, and 5 -- reads the ownershipDocument XML directly.

Person Consumer Contract ticket 19. Until PARSER_VERSION 2 this module handed
the artifact to ``edgar.ownership.Ownership.from_xml``, which looks every
reporting owner up on the SEC submissions API *at parse time* to decide
whether the owner is a company (``Entity(int(cik)).data.is_company``). That
was one live SEC request per reporting owner per parse, outside every
artifact-fetch policy, and the classification it computed was discarded --
only its side effect survived: an individual's ``rptOwnerName`` ("COOK
TIMOTHY D") was reversed to "Timothy D Cook" before landing in silver.

This version makes zero requests. The caller supplies ``submissions_lookup``,
a function from owner CIK to that CIK's bronze ``submissions.json`` payload
(or None when bronze has none); the same edgartools classifier
(``_classify_is_individual``) runs over that payload, so ``owner_name`` comes
out exactly as before. Every other pre-existing column is produced with the
same value semantics edgartools gave it: ``child_value`` fields keep their
" [F1]" footnote-marker suffix, ``child_text`` fields do not, "See Remarks"
titles are replaced by the remarks text. What is new on the owner row is the
classification evidence rule C-J reads (docs/specs/person/consumer.md):
``owner_name_raw`` (the registry name as disseminated, before any display
reversal), ``other_text``, the document's footnotes and remarks, two address
booleans, and the seven structural fields from submissions.json.

A transaction carries no owner reference in the SEC schema
(``NONDERIVATIVE_TRANSACTION`` / ``DERIVATIVE_TRANSACTION``, Ownership XML
Technical Specification), so on a joint filing it cannot be attributed to
one reporting owner. Transaction rows keep ``owner_index = 1`` (the landing
key) and carry ``reporting_owner_count`` and the free-text
``ownership_nature`` -- what the artifact does say -- so a consumer can fail
closed on ``reporting_owner_count > 1``.
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from collections.abc import Callable, Mapping
from typing import Any

# Kept from the edgartools-backed version so owner_name is byte-identical:
# reverse_name is the display transform it applied to individuals, and
# _classify_is_individual is the 9-signal chain Entity.data.is_company ran
# over the live submissions payload. Both exist in every edgartools release
# this repo has pinned (5.30.0 through 5.58.0); a move would fail here at
# import, loudly, not silently change owner_name.
from edgar.display.formatting import reverse_name
from edgar.entity.constants import _classify_is_individual

_DATE_PREFIX = re.compile(r"^\d{4}-\d{2}-\d{2}")
_XML_DECLARATION = re.compile(r"^<\?xml[^>]*\?>")
_CONTROL_CHARS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")

PARSER_NAME = "ownership_v1"
PARSER_VERSION = "3"

# CIK -> that CIK's bronze submissions.json payload, or None. A payload may
# carry SNAPSHOT_SHA256_KEY (SEC's own keys never start with "_"): the
# SHA-256 of the bronze object it was read from, recorded on the owner row so
# a rule C-J verdict names the snapshot it was computed from.
SubmissionsLookup = Callable[[int], Mapping[str, Any] | None]
SNAPSHOT_SHA256_KEY = "_bronze_sha256"

_EMPTY_RESULT: dict[str, list[dict[str, Any]]] = {
    "sec_ownership_reporting_owner": [],
    "sec_ownership_non_derivative_txn": [],
    "sec_ownership_derivative_txn": [],
}


def parse_ownership(
    accession_number: str,
    content: str,
    form_type: str,
    *,
    submissions_lookup: SubmissionsLookup | None = None,
) -> dict[str, list[dict[str, Any]]]:
    root = _ownership_root(content)
    if root is None:
        return {name: [] for name in _EMPTY_RESULT}

    issuer_cik = _parse_cik(_text(root, "./issuer/issuerCik"))
    remarks = _text(root, "./remarks")
    footnote_text = " | ".join(
        f"[{fn.get('id', '')}] {''.join(fn.itertext()).strip()}".strip()
        for fn in root.findall("./footnotes/footnote")
    )
    owner_elements = root.findall("./reportingOwner")
    reporting_owner_count = len(owner_elements)

    submissions_cache: dict[int | None, Mapping[str, Any] | None] = {}

    def _submissions(cik: int | None) -> Mapping[str, Any] | None:
        if cik not in submissions_cache:
            submissions_cache[cik] = (
                submissions_lookup(cik) if submissions_lookup is not None and cik is not None else None
            )
        return submissions_cache[cik]

    owner_rows: list[dict[str, Any]] = []
    for owner_index, owner in enumerate(owner_elements, start=1):
        owner_cik = _parse_cik(_text(owner, "./reportingOwnerId/rptOwnerCik"))
        raw_name = _text(owner, "./reportingOwnerId/rptOwnerName")
        payload = _submissions(owner_cik)
        officer_title = _text(owner, "./reportingOwnerRelationship/officerTitle")
        if officer_title and "see remarks" in officer_title.lower():
            officer_title = remarks
        owner_rows.append(
            {
                "accession_number": accession_number,
                "owner_index": owner_index,
                "owner_cik": owner_cik,
                "owner_name": raw_name if _is_company(owner_cik, payload) else reverse_name(raw_name),
                # The registry name exactly as EDGAR disseminated it ("COOK
                # TIMOTHY D"); owner_name above is edgartools' display
                # reversal, kept for continuity. The Person normalizer parses
                # this form (consumer.md; research 21).
                "owner_name_raw": raw_name,
                "is_director": _flag(owner, "./reportingOwnerRelationship/isDirector"),
                "is_officer": _flag(owner, "./reportingOwnerRelationship/isOfficer"),
                "is_ten_percent_owner": _flag(owner, "./reportingOwnerRelationship/isTenPercentOwner"),
                "is_other": _flag(owner, "./reportingOwnerRelationship/isOther"),
                "officer_title": officer_title or None,
                "issuer_cik": issuer_cik,
                # Ticket 19 item 1: deputization and self-description evidence.
                "other_text": _text(owner, "./reportingOwnerRelationship/otherText"),
                "filing_footnote_text": footnote_text,
                "filing_remarks": remarks,
                # Ticket 19 item 3: the address reduces to two booleans; no
                # street, city, state or zip leaves this function.
                "address_is_care_of": _text(owner, "./reportingOwnerAddress/rptOwnerStreet1")
                .upper().replace(" ", "").startswith("C/O"),
                "address_non_us": _flag(owner, "./reportingOwnerAddress/rptOwnerNonUSAddressFlag"),
                # Ticket 19 item 2: rule C-J's structural fields, from bronze.
                **_submissions_evidence(payload),
                "parser_version": PARSER_VERSION,
            }
        )

    # txn_index numbers the transactions kept, as edgartools did: an element
    # missing a schema-required block is dropped, not counted.
    non_derivative_rows: list[dict[str, Any]] = []
    kept = [
        txn for txn in root.findall("./nonDerivativeTable/nonDerivativeTransaction")
        if _has_children(txn, "transactionAmounts", "ownershipNature", "postTransactionAmounts")
    ]
    for txn_index, txn in enumerate(kept, start=1):
        non_derivative_rows.append(
            {
                "accession_number": accession_number,
                "owner_index": 1,
                "txn_index": txn_index,
                **_transaction_fields(txn),
                "reporting_owner_count": reporting_owner_count,
                "parser_version": PARSER_VERSION,
            }
        )

    derivative_rows: list[dict[str, Any]] = []
    kept = [
        txn for txn in root.findall("./derivativeTable/derivativeTransaction")
        if _has_children(txn, "transactionAmounts", "underlyingSecurity", "ownershipNature", "postTransactionAmounts")
    ]
    for txn_index, txn in enumerate(kept, start=1):
        derivative_rows.append(
            {
                "accession_number": accession_number,
                "owner_index": 1,
                "txn_index": txn_index,
                **_transaction_fields(txn),
                "conversion_or_exercise_price": _to_float(_value(txn, "./conversionOrExercisePrice")),
                "exercise_date": _to_date_str(_value(txn, "./exerciseDate")),
                "expiration_date": _to_date_str(_value(txn, "./expirationDate")),
                "underlying_security_title": _value_with_footnotes(txn, "./underlyingSecurity/underlyingSecurityTitle"),
                "underlying_security_shares": _to_float(_value(txn, "./underlyingSecurity/underlyingSecurityShares")),
                "reporting_owner_count": reporting_owner_count,
                "parser_version": PARSER_VERSION,
            }
        )

    return {
        "sec_ownership_reporting_owner": owner_rows,
        "sec_ownership_non_derivative_txn": non_derivative_rows,
        "sec_ownership_derivative_txn": derivative_rows,
    }


def _transaction_fields(txn: ET.Element) -> dict[str, Any]:
    """The eleven columns non-derivative and derivative transaction rows share."""
    return {
        "security_title": _value_with_footnotes(txn, "./securityTitle"),
        "transaction_date": _to_date_str(_value(txn, "./transactionDate")),
        "transaction_code": _text(txn, "./transactionCoding/transactionCode"),
        "transaction_shares": _to_float(_text(txn, "./transactionAmounts/transactionShares")),
        "transaction_price": _to_float(_text(txn, "./transactionAmounts/transactionPricePerShare")),
        "acquired_disposed_code": _text(txn, "./transactionAmounts/transactionAcquiredDisposedCode"),
        "shares_owned_after": _to_float(_text(txn, "./postTransactionAmounts/sharesOwnedFollowingTransaction")),
        "ownership_direct_indirect": _text(txn, "./ownershipNature/directOrIndirectOwnership"),
        "ownership_nature": _text(txn, "./ownershipNature/natureOfOwnership"),
    }


_STRUCTURAL_EMPTY: dict[str, Any] = {
    "owner_submissions_present": False,
    "owner_submissions_sha256": "",
    "owner_entity_type": "",
    "owner_sic": "",
    "owner_state_of_incorporation": "",
    "owner_ein": "",
    "owner_ticker_count": 0,
    "owner_org": "",
    "owner_fiscal_year_end": "",
}


def _submissions_evidence(payload: Mapping[str, Any] | None) -> dict[str, Any]:
    """Rule C-J's structural fields (consumer.md, step 3), as text with ""
    for absent -- the rule tests presence, and a stable non-null column type
    survives a run where every value is absent."""
    if payload is None:
        return dict(_STRUCTURAL_EMPTY)
    return {
        "owner_submissions_present": True,
        "owner_submissions_sha256": _json_text(payload.get(SNAPSHOT_SHA256_KEY)),
        "owner_entity_type": _json_text(payload.get("entityType")),
        "owner_sic": _json_text(payload.get("sic")),
        "owner_state_of_incorporation": _json_text(payload.get("stateOfIncorporation")),
        "owner_ein": _json_text(payload.get("ein")),
        "owner_ticker_count": len(payload.get("tickers") or []),
        "owner_org": _json_text(payload.get("ownerOrg")),
        "owner_fiscal_year_end": _json_text(payload.get("fiscalYearEnd")),
    }


def _is_company(cik: int | None, payload: Mapping[str, Any] | None) -> bool:
    """edgartools 5.30.0's ``entity and entity.data.is_company``, fed from bronze.

    With no payload the owner is not a company, so its name is reversed --
    the same result edgartools reached for a CIK the SEC lookup did not find
    (``Entity.__bool__`` is false, so ``entity and ...`` short-circuits). A
    missing snapshot therefore changes owner_name as well as the evidence:
    an entity owner with no bronze snapshot gets a reversed name.
    """
    if payload is None:
        return False
    forms = list((payload.get("filings") or {}).get("recent", {}).get("form") or [])[:50]
    return not _classify_is_individual(
        name=payload.get("name"),
        tickers=payload.get("tickers"),
        exchanges=payload.get("exchanges"),
        state_of_incorporation=payload.get("stateOfIncorporation"),
        entity_type=payload.get("entityType"),
        forms=forms,
        ein=payload.get("ein"),
        cik=cik,
        insider_transaction_for_issuer_exists=bool(payload.get("insiderTransactionForIssuerExists")),
        insider_transaction_for_owner_exists=bool(payload.get("insiderTransactionForOwnerExists")),
    )


def _ownership_root(content: str) -> ET.Element | None:
    """The <ownershipDocument> element from a bare primary document or a full
    SEC .txt submission (SGML header + <XML>...</XML>); None when the payload
    is neither."""
    i = content.find("<XML>")
    j = content.rfind("</XML>")
    xml = content[i + 5 : j] if i >= 0 and j > i else content
    xml = _XML_DECLARATION.sub("", xml.strip()).strip()
    try:
        root = ET.fromstring(xml)
    except ET.ParseError:
        try:
            root = ET.fromstring(_CONTROL_CHARS.sub("", xml))
        except ET.ParseError:
            return None
    return root if root.tag == "ownershipDocument" else None


def _has_children(el: ET.Element, *tags: str) -> bool:
    return all(el.find(tag) is not None for tag in tags)


def _text(el: ET.Element | None, path: str) -> str:
    """Stripped text of the first element at ``path`` (edgartools' child_text:
    all descendant text, stripped), "" when absent."""
    if el is None:
        return ""
    found = el.find(path)
    return "".join(found.itertext()).strip() if found is not None else ""


def _value(el: ET.Element, path: str) -> str | None:
    found = el.find(path)
    if found is None:
        return None
    value = found.find("value")
    return value.text if value is not None else None


def _value_with_footnotes(el: ET.Element, path: str) -> str:
    """edgartools' child_value / value_with_footnotes: "<value> [F1,F2]"."""
    found = el.find(path)
    if found is None:
        return ""
    value_el = found.find("value")
    value = (value_el.text or "") if value_el is not None else ""
    ids = ",".join(fn.get("id", "") for fn in found.findall("footnoteId") if fn.get("id"))
    marker = f"[{ids}]" if ids else ""
    if value:
        return f"{value} {marker}" if marker else value
    return marker


def _flag(el: ET.Element, path: str) -> bool:
    """edgartools' get_bool over child_text; also covers the xs:boolean
    lexical forms the address flag uses ("true"/"false")."""
    return _text(el, path) in ("1", "Y", "true", "True", "TRUE")


def _json_text(value: Any) -> str:
    return "" if value is None else str(value)


def _parse_cik(value: Any) -> int | None:
    try:
        return int(str(value)) if value else None
    except (ValueError, TypeError):
        return None


def _to_float(value: Any) -> float | None:
    try:
        return float(value) if value not in (None, "") else None
    except (TypeError, ValueError):
        return None


def _to_date_str(value: Any) -> str | None:
    """Extract a leading YYYY-MM-DD date from a raw filing value.

    SEC Form 3/4/5 XML legitimately attaches footnote markers (e.g.
    "2021-02-04 [F2]") to date fields. DuckDB's implicit VARCHAR->DATE cast
    silently truncates such values, but Snowflake's COPY INTO cast is
    strict and rejects them outright -- aborting the whole silver-landing
    load for every table, not just this row. Normalize at the source so
    both consumers see the same clean value.
    """
    if value is None:
        return None
    s = str(value)
    match = _DATE_PREFIX.match(s)
    return match.group(0) if match else None
