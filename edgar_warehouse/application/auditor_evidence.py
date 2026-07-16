"""Direct annual-filing and PCAOB identity ingestion for AUDITED_BY."""

from __future__ import annotations

import csv
import hashlib
import io
import re
from dataclasses import asdict, dataclass
from datetime import date, datetime

from bs4 import BeautifulSoup

from edgar_warehouse.application.errors import WarehouseRuntimeError


@dataclass(frozen=True)
class AuditorEvidenceRow:
    accession_number: str
    registrant_cik: int
    form_type: str
    document_name: str
    audited_period_end: date
    report_date: date
    principal_firm_name: str
    principal_firm_location: str
    pcaob_firm_id: str
    evidence_source: str
    raw_locator: str
    source_sha256: str
    evidence_fingerprint: str
    form_ap_filing_id: str | None = None
    original_form_ap_filing_id: str | None = None
    latest_amendment: bool | None = None


@dataclass(frozen=True)
class AuditorParseResult:
    outcome: str
    reason: str | None
    row: AuditorEvidenceRow | None


@dataclass(frozen=True)
class PcaobFirmIdentity:
    pcaob_firm_id: str
    canonical_name: str
    city: str | None
    state: str | None
    country: str | None
    status: str | None
    snapshot_uri: str
    snapshot_sha256: str


def _clean(value: str) -> str:
    return " ".join(value.replace("\xa0", " ").split())


def normalize_pcaob_firm_id(value: object) -> str:
    raw = _clean(str(value or ""))
    if not raw.isdecimal():
        raise WarehouseRuntimeError(f"invalid PCAOB Firm ID: {raw!r}")
    return str(int(raw))


def _local_name(tag: object) -> str:
    name = str(getattr(tag, "name", ""))
    return name.rsplit(":", 1)[-1].lower()


def parse_auditor_evidence(
    *,
    accession_number: str,
    registrant_cik: int,
    form_type: str,
    document_name: str,
    content: bytes | str,
    audited_period_end: date,
    filing_date: date,
    source_sha256: str,
) -> AuditorParseResult:
    """Extract one complete direct-filing auditor triplet, failing on ambiguity."""
    normalized_form = form_type.upper().replace("/A", "")
    if normalized_form not in {"10-K", "20-F", "40-F"}:
        raise WarehouseRuntimeError(f"unsupported annual auditor form: {form_type}")
    if not accession_number or registrant_cik <= 0 or not document_name or not source_sha256:
        raise WarehouseRuntimeError("auditor evidence is missing required lineage")
    text = content.decode("utf-8", errors="replace") if isinstance(content, bytes) else str(content)
    soup = BeautifulSoup(text, "html.parser")
    concepts = {
        "auditorname": "name",
        "auditorfirmid": "firm_id",
        "auditorlocation": "location",
    }
    by_context: dict[str, dict[str, str]] = {}
    found_any = False
    for tag in soup.find_all(True):
        key = concepts.get(_local_name(tag))
        if key is None:
            continue
        found_any = True
        context = str(tag.get("contextref") or tag.get("contextRef") or "")
        if not context:
            raise WarehouseRuntimeError("auditor fact has no contextRef")
        value = _clean(tag.get_text(" ", strip=True))
        prior = by_context.setdefault(context, {}).get(key)
        if prior is not None and prior != value:
            raise WarehouseRuntimeError(f"conflicting auditor facts in context {context}")
        by_context[context][key] = value
    if found_any:
        complete = [(context, values) for context, values in by_context.items()
                    if set(values) == {"name", "firm_id", "location"}]
        if not complete:
            raise WarehouseRuntimeError("incomplete auditor triplet")
        unique = {(v["name"], normalize_pcaob_firm_id(v["firm_id"]), v["location"])
                  for _, v in complete}
        if len(unique) != 1:
            raise WarehouseRuntimeError("multiple conflicting primary auditor contexts")
        context, values = sorted(complete)[0]
        return _result(
            accession_number, registrant_cik, normalized_form, document_name,
            audited_period_end, filing_date, values["name"], values["location"],
            values["firm_id"], "sec_ixbrl", f"context:{context}", source_sha256,
        )

    # The fallback is deliberately bounded to the independent-auditor report and
    # its signature. It will not guess a firm when the required markers are absent.
    plain = soup.get_text("\n", strip=True)
    heading = re.search(
        r"report of independent registered public accounting firm", plain, re.I
    )
    if not heading:
        return AuditorParseResult("unresolved", "auditor_report_not_found", None)
    bounded = plain[heading.start():heading.start() + 30000]
    signature = re.search(
        r"/s/\s*([^\n]{3,200})\n\s*([^\n]{2,160})\n\s*(?:[A-Za-z]+\s+\d{1,2},\s+\d{4})",
        bounded,
    )
    firm_id = re.search(r"PCAOB(?:\s+Firm)?(?:\s+ID|\s+No\.)?\s*[:#]?\s*(\d+)", bounded, re.I)
    report_date = re.search(r"([A-Za-z]+\s+\d{1,2},\s+\d{4})", bounded)
    if not (signature and firm_id and report_date):
        return AuditorParseResult("unresolved", "bounded_report_signature_incomplete", None)
    parsed_date = datetime.strptime(report_date.group(1), "%B %d, %Y").date()
    return _result(
        accession_number, registrant_cik, normalized_form, document_name,
        audited_period_end, parsed_date, signature.group(1), signature.group(2),
        firm_id.group(1), "sec_auditor_report", "independent-auditor-report/signature",
        source_sha256,
    )


def _result(
    accession_number: str, registrant_cik: int, form_type: str, document_name: str,
    audited_period_end: date, report_date: date, name: str, location: str,
    firm_id: str, source: str, locator: str, source_sha256: str,
) -> AuditorParseResult:
    normalized_id = normalize_pcaob_firm_id(firm_id)
    fingerprint = hashlib.sha256(
        "|".join((accession_number, str(registrant_cik), normalized_id,
                  report_date.isoformat(), source_sha256, locator)).encode()
    ).hexdigest()
    row = AuditorEvidenceRow(
        accession_number=accession_number, registrant_cik=registrant_cik,
        form_type=form_type, document_name=document_name,
        audited_period_end=audited_period_end, report_date=report_date,
        principal_firm_name=_clean(name), principal_firm_location=_clean(location),
        pcaob_firm_id=normalized_id, evidence_source=source,
        raw_locator=locator, source_sha256=source_sha256,
        evidence_fingerprint=fingerprint,
    )
    return AuditorParseResult("applicable_loaded", None, row)


def parse_pcaob_firm_registry(
    content: bytes | str, *, snapshot_uri: str, snapshot_sha256: str
) -> tuple[PcaobFirmIdentity, ...]:
    """Parse a complete PCAOB firm snapshot without a top-firm cap."""
    text = content.decode("utf-8-sig") if isinstance(content, bytes) else str(content)
    reader = csv.DictReader(io.StringIO(text))
    if not reader.fieldnames:
        raise WarehouseRuntimeError("PCAOB registry has no header")
    rows: dict[str, PcaobFirmIdentity] = {}
    for raw in reader:
        firm_id = normalize_pcaob_firm_id(raw.get("Firm ID"))
        name = _clean(raw.get("Firm Name") or "")
        if not name:
            raise WarehouseRuntimeError(f"PCAOB firm {firm_id} has no name")
        identity = PcaobFirmIdentity(
            firm_id, name, raw.get("City") or None, raw.get("State") or None,
            raw.get("Country") or None, raw.get("Status") or None,
            snapshot_uri, snapshot_sha256,
        )
        prior = rows.get(firm_id)
        if prior and prior != identity:
            raise WarehouseRuntimeError(f"conflicting PCAOB firm identity: {firm_id}")
        rows[firm_id] = identity
    return tuple(rows[key] for key in sorted(rows, key=int))


def ingest_auditor_parse_result(db: object, result: AuditorParseResult, *, sync_run_id: str) -> int:
    if result.row is None:
        return 0
    return db.merge_auditor_report_evidence([asdict(result.row)], sync_run_id)
