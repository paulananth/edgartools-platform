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
_NAME = r"[A-Z][A-Za-z'.-]+(?:\s+(?:[A-Z][A-Za-z'.-]+|[A-Z]\.?)){1,4}"
_ROLE = r"[A-Z][A-Za-z/& -]{2,80}?"
_NAME_LIST = rf"{_NAME}(?:\s*,\s*{_NAME})*(?:\s*,?\s+and\s+{_NAME})?"
# Passive voice: "[Name] was/has been/will be appointed as [Role]". Historically the
# only shape this parser recognized.
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
# Active voice: "the Board/Company ... appointed/elected/named [Name(s)] as [Role]".
# This is the dominant real-world 8-K phrasing (company/board as grammatical
# subject) — see item_502 active-voice-coverage 5-whys. Supports Oxford-comma
# multi-person lists ("appointed A, B, and C as directors").
_ACTIVE_APPOINTMENT = re.compile(
    rf"(?:appointed|elected|named)\s+(?P<names>{_NAME_LIST})\s+as\s+(?P<role>{_ROLE})(?=[,.\s])",
    re.I,
)
# "[Committee] elected [Name(s)] to fill [a/the] vacancy [on the Board]" — no
# explicit role stated; filling a board vacancy is a director appointment.
_ACTIVE_APPOINTMENT_VACANCY = re.compile(
    rf"elected\s+(?P<names>{_NAME_LIST})\s+to\s+fill\s+(?:a|the)\s+vacancy",
    re.I,
)
# "[Company] terminated the employment of [Name]" — active-voice termination.
_ACTIVE_TERMINATION = re.compile(
    rf"terminated\s+the\s+employment\s+of\s+(?P<name>{_NAME})",
    re.I,
)
_LEADING_DATE = re.compile(rf"(?:On|Effective)\s+(?P<date>{_DATE}),", re.I)
_TRAILING_DATE = re.compile(rf"effective\s+(?:as of\s+)?(?P<date>{_DATE})", re.I)
_TRAILING_IMMEDIATE = re.compile(r"effective\s+immediately", re.I)
_ITEM_HEADER = re.compile(r"item\s+(\d{1,2})\s*\.\s*(\d{2})\b", re.I)
_DATE_WINDOW = 160


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


def _clean_name(name: str) -> str:
    """Normalize whitespace and drop a trailing sentence period the greedy
    `_NAME` pattern swallows when a name sits at the end of a sentence."""
    return re.sub(r"\s+", " ", name).strip().rstrip(".")


def _split_names(names_text: str) -> list[str]:
    """Split an Oxford-comma-joined name list ("A, B, and C") into individual names."""
    return [_clean_name(name) for name in re.findall(_NAME, names_text)]


def _resolve_active_voice_date(section: str, match: re.Match, filing_date: date) -> date | None:
    """Find the effective date for an active-voice event match.

    Active-voice 8-K sentences put the date in one of three places: right after
    the clause ("... as director, effective March 1, 2026" / "effective
    immediately"), or as a lead-in before the whole sentence ("On March 1, 2026,
    the Board appointed ..."). Returns None (fail closed, no guessing) if no date
    can be confidently located in either position.
    """
    trailing_window = section[match.end():match.end() + _DATE_WINDOW]
    trailing_match = _TRAILING_DATE.search(trailing_window)
    if trailing_match:
        return _parse_date(trailing_match.group("date"))
    if _TRAILING_IMMEDIATE.search(trailing_window[:40]):
        return filing_date
    leading_window = section[max(0, match.start() - _DATE_WINDOW):match.start()]
    leading_matches = list(_LEADING_DATE.finditer(leading_window))
    if leading_matches:
        return _parse_date(leading_matches[-1].group("date"))
    return None


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
    for match in _ACTIVE_APPOINTMENT.finditer(section):
        effective_date = _resolve_active_voice_date(section, match, filing_date)
        if effective_date is None:
            continue
        role = re.sub(r"\s+", " ", match.group("role")).strip(" ,.")
        for name in _split_names(match.group("names")):
            events.append(EmploymentEvent(
                accession_number, int(cik), "appointment", name, role, effective_date,
            ))
    for match in _ACTIVE_APPOINTMENT_VACANCY.finditer(section):
        effective_date = _resolve_active_voice_date(section, match, filing_date)
        if effective_date is None:
            continue
        for name in _split_names(match.group("names")):
            events.append(EmploymentEvent(
                accession_number, int(cik), "appointment", name, "Director", effective_date,
            ))
    for match in _ACTIVE_TERMINATION.finditer(section):
        effective_date = _resolve_active_voice_date(section, match, filing_date)
        if effective_date is None:
            continue
        events.append(EmploymentEvent(
            accession_number, int(cik), "departure",
            _clean_name(match.group("name")), None, effective_date,
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
