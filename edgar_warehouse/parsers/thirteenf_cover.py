"""Parse release-critical Form 13F cover-page amendment metadata."""

from __future__ import annotations

from xml.etree import ElementTree


def _values(root: ElementTree.Element) -> dict[str, str]:
    result: dict[str, str] = {}
    for element in root.iter():
        name = element.tag.rsplit("}", 1)[-1].casefold()
        if element.text and element.text.strip():
            result[name] = element.text.strip()
    return result


def parse_thirteenf_cover(content: str) -> dict[str, bool | str | None]:
    values = _values(ElementTree.fromstring(content))
    is_amendment = values.get("isamendment", "false").casefold() in {"true", "1", "yes"}
    raw_type = values.get("amendmenttype", "").strip().casefold()
    if not is_amendment:
        amendment_type = None
    elif raw_type in {"restatement", "restated"}:
        amendment_type = "restatement"
    elif raw_type in {"new holdings", "new holdings entries", "added holdings", "addition"}:
        amendment_type = "added_holdings"
    else:
        raise ValueError("13F amendment cover page has no recognized amendment type")
    confidential = values.get("confidentialomitted", "false").casefold() in {"true", "1", "yes"}
    # periodOfReport lives on the cover, usually as MM-DD-YYYY; normalize to
    # ISO. The quarterly SEC indexes (the freeze's 13F candidate source) carry
    # no reportDate at all, so the cover is the authoritative — and often the
    # only — period source for a 13F.
    period_of_report: str | None = None
    raw_period = values.get("periodofreport", "").strip()
    if raw_period:
        cleaned = raw_period.replace("/", "-")
        parts = cleaned.split("-")
        if len(parts) == 3 and len(parts[0]) == 4:
            period_of_report = cleaned[:10]
        elif len(parts) == 3 and len(parts[2]) == 4:
            period_of_report = f"{parts[2]}-{parts[0]:0>2}-{parts[1]:0>2}"
    return {
        "is_amendment": is_amendment,
        "amendment_type": amendment_type,
        "confidential_omission": confidential,
        "period_of_report": period_of_report,
    }
