"""Conservative Form 8-K Item 5.02 employment-event parser."""

from __future__ import annotations

import html
import re
from dataclasses import dataclass
from datetime import date, datetime
from typing import Iterable


PARSER_NAME = "item_502"
PARSER_VERSION = "1"


@dataclass(frozen=True)
class EmploymentEvent:
    accession_number: str
    cik: int
    event_type: str
    person_name: str
    role: str | None
    effective_date: date
    previous_role: str | None = None
    compensation_amount: float | None = None


@dataclass(frozen=True)
class Item502Result:
    applicability: str
    reason_code: str
    events: tuple[EmploymentEvent, ...]


@dataclass(frozen=True)
class EmploymentVersion:
    cik: int
    person_name: str
    role: str | None
    valid_from: date
    valid_to: date | None
    source_accession: str


_DATE = r"(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2},\s+\d{4}"
_NAME = r"[A-Z][A-Za-z'.-]+(?:\s+(?:[A-Z]\.?|[A-Z][A-Za-z'.-]+)){1,4}"
_ROLE = r"[A-Z][A-Za-z/& -]{2,80}?"
_APPOINTMENT = re.compile(
    rf"(?P<name>{_NAME})\s+(?:was|has been|will be)\s+(?:elected|appointed|named)\s+(?:to serve\s+)?as\s+(?P<role>{_ROLE})(?:,|\s+effective).*?(?:effective\s+)?(?P<date>{_DATE})",
    re.I,
)
_DEPARTURE = re.compile(
    rf"(?P<name>{_NAME})\s+(?:resigned|retired|departed|was terminated|ceased to serve)\s+(?:from (?:the )?(?:position|role) of|as)?\s*(?P<role>{_ROLE})?(?:,|\s+effective).*?(?:effective\s+)?(?P<date>{_DATE})",
    re.I,
)
_ROLE_CHANGE = re.compile(
    rf"(?P<name>{_NAME})\s+(?:was|has been|will be)\s+(?:promoted|transitioned|moved)\s+"
    rf"from\s+(?P<previous>{_ROLE})\s+to\s+(?P<role>{_ROLE})(?:,|\s+effective).*?"
    rf"(?:effective\s+)?(?P<date>{_DATE})",
    re.I,
)
_COMPENSATION = re.compile(
    rf"(?:approved|set|increased)\s+(?:an?\s+)?(?:annual\s+)?(?:base\s+)?salary\s+of\s+"
    rf"\$(?P<amount>[\d,]+(?:\.\d{{2}})?)\s+for\s+(?P<name>{_NAME}).*?"
    rf"(?:effective\s+)?(?P<date>{_DATE})",
    re.I,
)
_ITEM_HEADER = re.compile(r"item\s+(\d{1,2})\s*\.\s*(\d{2})\b", re.I)


def _text(content: str) -> str:
    without_tags = re.sub(r"<[^>]+>", " ", content)
    return re.sub(r"\s+", " ", html.unescape(without_tags)).strip()


def _item_502_section(text: str) -> str:
    """Scope matching to the Item 5.02 section only.

    Multi-item 8-Ks (e.g. 5.02 + 5.07 annual-meeting filings) repeat action verbs
    like "named"/"elected" in unrelated sections (Item 5.07 vote tallies). Matching
    the whole document lets that unrelated text falsely trip the unresolved-event
    fallback below, so bound the search to the last "Item 5.02" heading (skipping
    earlier cover-page item enumerations) through the next differing item header.
    """
    headers = list(_ITEM_HEADER.finditer(text))
    section_starts = [m for m in headers if m.group(1) == "5" and m.group(2) == "02"]
    if not section_starts:
        return text
    start = section_starts[-1].start()
    end = len(text)
    for match in headers:
        if match.start() > start and (match.group(1), match.group(2)) != ("5", "02"):
            end = match.start()
            break
    return text[start:end]


def _parse_date(value: str) -> date:
    return datetime.strptime(value, "%B %d, %Y").date()


def parse_item_502(*, accession_number: str, cik: int, filing_date: date,
                   content: str) -> Item502Result:
    text = _text(content)
    if not re.search(r"item\s+5\s*\.\s*02", text, re.I):
        return Item502Result("not_applicable", "item_5_02_absent", ())
    section = _item_502_section(text)
    events: list[EmploymentEvent] = []
    for event_type, pattern in (("appointment", _APPOINTMENT), ("departure", _DEPARTURE)):
        for match in pattern.finditer(section):
            role = re.sub(r"\s+", " ", (match.group("role") or "")).strip(" ,.") or None
            events.append(EmploymentEvent(
                accession_number, int(cik), event_type,
                re.sub(r"\s+", " ", match.group("name")).strip(), role,
                _parse_date(match.group("date")),
            ))
    for match in _ROLE_CHANGE.finditer(section):
        events.append(EmploymentEvent(
            accession_number, int(cik), "role_change", match.group("name").strip(),
            match.group("role").strip(" ,."), _parse_date(match.group("date")),
            previous_role=match.group("previous").strip(" ,."),
        ))
    for match in _COMPENSATION.finditer(section):
        events.append(EmploymentEvent(
            accession_number, int(cik), "compensation_change", match.group("name").strip(),
            None, _parse_date(match.group("date")),
            compensation_amount=float(match.group("amount").replace(",", "")),
        ))
    if events:
        events.sort(key=lambda row: (row.effective_date, row.person_name, row.event_type))
        return Item502Result("applicable", "named_employment_event", tuple(events))
    if re.search(r"\b(appointed|elected|named|resigned|retired|departed|terminated|ceased to serve)\b", section, re.I):
        return Item502Result("unresolved", "unclassified_named_event", ())
    return Item502Result("not_applicable", "no_named_employment_event", ())


def apply_employment_events(
    baselines: Iterable[EmploymentVersion], events: Iterable[EmploymentEvent]
) -> tuple[EmploymentVersion, ...]:
    versions = list(baselines)
    for event in sorted(events, key=lambda row: (row.effective_date, row.accession_number)):
        matching = [
            (index, row) for index, row in enumerate(versions)
            if row.cik == event.cik and row.person_name.casefold() == event.person_name.casefold()
            and row.valid_to is None
        ]
        if event.event_type in {"appointment", "role_change", "compensation_change"}:
            if matching:
                current = matching[-1][1]
                next_role = event.role or current.role
                if event.event_type == "appointment" and (
                    (current.role or "").casefold() == (next_role or "").casefold()
                ):
                    continue
                versions[matching[-1][0]] = EmploymentVersion(
                    current.cik, current.person_name, current.role, current.valid_from,
                    event.effective_date, current.source_accession,
                )
            versions.append(EmploymentVersion(
                event.cik, event.person_name,
                event.role or (matching[-1][1].role if matching else None),
                event.effective_date, None,
                event.accession_number,
            ))
        elif event.event_type == "departure":
            if len(matching) != 1:
                raise ValueError(f"departure does not resolve one current employment: {event.accession_number}")
            index, current = matching[0]
            versions[index] = EmploymentVersion(
                current.cik, current.person_name, current.role, current.valid_from,
                event.effective_date, current.source_accession,
            )
        else:
            raise ValueError(f"unknown employment event type: {event.event_type}")
    return tuple(sorted(versions, key=lambda row: (row.cik, row.person_name.casefold(), row.valid_from)))
