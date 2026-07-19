"""Conservative Form 8-K Item 5.02 employment-event parser.

Uses spaCy dependency parsing + NER for appointment/departure extraction
instead of hand-written regex. Regex could only be taught one surface phrasing
at a time (passive voice, then active voice, then vacancy-filling, ...) and a
528k-candidate production survey showed real 8-Ks vary far more than any
regex list could keep up with. Dependency parsing captures the underlying
grammatical relation (who is the subject/object of "appointed") regardless of
voice or word order, so active and passive phrasing fall out of the same
extraction code path, and it also gives a structural signal (conditional
`mark` children on the event verb) to reject hypothetical/plan-boilerplate
language ("as if the participant retired...") without guessing semantically.

`_ROLE_CHANGE`/`_COMPENSATION` stay regex-based: narrower, well-defined shapes
that were not the source of the coverage gap.

Coverage evolution:
- PR #146: section-scope ambiguity to Item 5.02 only
- PR #154: active-voice regex
- PR #155: spaCy rewrite
- PR #157: possessive departures + modifier participles
- v3: board appointments without "as", expanded verbs
  (join/hire/leave/step-down), filing-date fallback when person+role resolved,
  particle "step down", and title-boilerplate verbs ignored for unresolved
- v4: bulleted committee/director rosters ("appointed X to serve as Y and
  appointed the following directors to committees: • Audit Committee: ...")
  carry no sentence-ending punctuation, so the intro clause and the whole
  bulleted list read to spaCy as one run-on sentence; the resulting
  low-confidence parse sometimes misattaches a real, preceding appointment
  clause as subordinate to unrelated text after the list. Bullets are now
  normalized to sentence breaks before parsing (production scope check:
  9.5% unresolved rate across a 400-sample scan of the Item 5.02 universe;
  fixture is CIK 88000 / accession 0000950170-24-098502).
- v5: a 2,000-sample scope check after v4 found the aggregate unresolved
  rate (~10.6%) barely moved and traced it to several distinct patterns
  under the "appoint" trigger. The dominant one by far turned out to be the
  bare object-predicate role shape with NO preposition at all — "[Person]
  was appointed [Role] of [Company]" (dependency label `oprd` on the role
  noun) — which `_find_role` never checked; it only recognized "as [Role]"
  and "to the position/role/office of [Role]". Also added "promoted to
  [Role]" as a direct-object-style role for "promote" specifically (kept
  narrowly scoped to that verb — broadening the general "to [NOUN]" case
  for every appointment verb would risk matching unrelated destinations,
  e.g. "appointed X to the Committee"). Both are purely additive
  under-extraction fixes: they can only turn a real, already-disclosed
  person+role+date into a resolved event, never fabricate one, so they
  carry no false-positive risk. Deliberately NOT fixed here: backward-
  references to prior filings ("as previously disclosed... had appointed"),
  bio-background prose, appositive names, and nominalized "approved the
  appointment of X" — those are suppression-shaped fixes (would turn
  `unresolved` into `not_applicable`, which release_mode does not
  re-check) and can silently drop a real event if the same filing also
  discloses one under a different construction (confirmed on a real
  accession); left as pending backlog rather than rushed.
"""

from __future__ import annotations

import html
import re
from dataclasses import dataclass
from datetime import date, datetime
from typing import Iterable

import spacy

PARSER_NAME = "item_502"
PARSER_VERSION = "5"


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
_ROLE = r"[A-Z][A-Za-z/& -]{2,80}?"
_ROLE_CHANGE = re.compile(
    rf"(?P<name>[A-Z][A-Za-z'.-]+(?:\s+[A-Z][A-Za-z'.-]+){{1,3}})\s+(?:was|has been|will be)\s+(?:promoted|transitioned|moved)\s+"
    rf"from\s+(?P<previous>{_ROLE})\s+to\s+(?P<role>{_ROLE})(?:,|\s+effective).*?"
    rf"(?:effective\s+)?(?P<date>{_DATE})",
    re.I,
)
_COMPENSATION = re.compile(
    rf"(?:approved|set|increased)\s+(?:an?\s+)?(?:annual\s+)?(?:base\s+)?salary\s+of\s+"
    rf"\$(?P<amount>[\d,]+(?:\.\d{{2}})?)\s+for\s+(?P<name>[A-Z][A-Za-z'.-]+(?:\s+[A-Z][A-Za-z'.-]+){{1,3}}).*?"
    rf"(?:effective\s+)?(?P<date>{_DATE})",
    re.I,
)
_ITEM_HEADER = re.compile(r"item\s+(\d{1,2})\s*\.\s*(\d{2})\b", re.I)
_TRAILING_IMMEDIATE = re.compile(r"effective\s+immediately", re.I)
_BOARD_DIRECTOR = re.compile(
    r"\b(?:board of directors|as (?:a )?directors?|to the board|on the board)\b",
    re.I,
)
# Statutory Item 5.02 title line only (not the body sentence after a bare "Item 5.02").
_SECTION_TITLE_SPAN = re.compile(
    r"^item\s+5\s*\.\s*02\s+"
    r"(?:departure|election|appointment|compensatory)[^.]{0,200}?\.",
    re.I,
)

_LIST_BULLETS = re.compile(r"\s*[•◦▪●]\s*")

_APPOINTMENT_VERBS = {"appoint", "elect", "name", "join", "hire", "promote"}
_DEPARTURE_VERBS = {
    "resign",
    "retire",
    "depart",
    "terminate",
    "leave",
    "separate",
    "dismiss",
    "step",  # "stepped down" with particle
}
_TENURE_NOUNS = {"employment", "service", "tenure", "position", "role"}
_DEPARTURE_NOUNS = {
    "resignation",
    "retirement",
    "departure",
    "separation",
    "termination",
}
_MODIFIER_DEPS = frozenset({"amod", "acl", "advcl", "relcl", "xcomp", "ccomp"})
_CONDITIONAL_MARKS = {"if", "unless", "whether"}
_MONTHS = (
    "January", "February", "March", "April", "May", "June", "July",
    "August", "September", "October", "November", "December",
)

_NLP: spacy.language.Language | None = None


def _nlp() -> spacy.language.Language:
    global _NLP
    if _NLP is None:
        _NLP = spacy.load("en_core_web_sm")
    return _NLP


def _text(content: str) -> str:
    without_tags = re.sub(r"<[^>]+>", " ", content)
    unescaped = html.unescape(without_tags)
    # Bulleted rosters (e.g. "appointed the following directors to committees:
    # • Audit Committee: ... • Compensation Committee: ...") carry no
    # sentence-ending punctuation in the source, so spaCy's segmenter reads the
    # intro clause plus the whole bulleted list as one run-on sentence. The
    # dependency parser then produces a low-confidence parse over that span,
    # sometimes misattaching a real appointment clause before the list as
    # subordinate to unrelated text after it. Force a sentence boundary at
    # each bullet so the list segments separately from the clause that precedes it.
    unescaped = _LIST_BULLETS.sub(". ", unescaped)
    return re.sub(r"\s+", " ", unescaped).strip()


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


def _is_hypothetical(verb) -> bool:
    """True if `verb` sits inside a conditional clause ("as if the participant
    retired...", describing a hypothetical plan provision) rather than a real
    disclosed event -- a structural signal from the dependency parse, not a
    semantic guess."""
    node = verb
    seen: set[int] = set()
    while node is not None and id(node) not in seen:
        seen.add(id(node))
        if node.dep_ in ("advcl", "relcl"):
            for child in node.children:
                if child.dep_ == "mark" and child.lower_ in _CONDITIONAL_MARKS:
                    return True
        if node.head is node:
            break
        node = node.head
    return False


def _person_name(token) -> str | None:
    """Reconstruct a full person name from a head noun token (e.g. the "Gutmann"
    token of "Kathleen M. Gutmann") by collecting its direct `compound`
    children (restricted to PROPN, so an unrelated preceding NOUN can't leak
    in) in document order. More robust than relying on NER span boundaries,
    which the small English model sometimes mis-tags (e.g. classifying a name
    as ORG in a multi-person list)."""
    if token.pos_ != "PROPN":
        return None
    parts = sorted(
        [c for c in token.children if c.dep_ == "compound" and c.pos_ == "PROPN"] + [token],
        key=lambda t: t.i,
    )
    name = " ".join(t.text for t in parts)
    name = re.sub(r"\s+", " ", name).strip().rstrip(".")
    # Require at least two capitalized components (first + last name) to avoid
    # false positives on bare common nouns.
    if len(re.findall(r"[A-Z][a-z]", name)) < 2:
        return None
    return name


def _expand_conjuncts(token) -> list:
    return [token] + list(token.conjuncts)


def _find_role_and_token(verb, sent):
    """"appointed X as [Role]", "appointed X to the position/role of [Role]",
    the bare "appointed X [Role]" object-predicate shape (dependency label
    `oprd` — no preposition at all, by far the most common real-8-K phrasing:
    "Lucy To ... was appointed Chief Financial Officer of SAB Biotherapeutics"),
    or, for "promote" specifically, "promoted X to [Role]" where [Role] is an
    arbitrary title rather than the literal word position/role/office/board
    (scoped to "promote" only — broadening the general "to [NOUN]" case for
    every appointment verb would risk matching unrelated destinations, e.g.
    "appointed X to the Committee").

    Returns (role_text, role_token) — role_token is the specific child token
    consumed as the role source so the caller can exclude it from person-
    candidate collection (an oprd role-noun phrase can otherwise look like a
    PROPN "name" to `_person_name`); role_token is None when role came from a
    sentence-level fallback with no single source token.
    """
    for child in verb.children:
        if child.dep_ == "prep" and child.lower_ == "as":
            pobj = next((c for c in child.children if c.dep_ == "pobj"), None)
            if pobj is not None:
                return _clean_span(pobj), pobj
        if child.dep_ == "prep" and child.lower_ == "to":
            noun = next((c for c in child.children if c.dep_ == "pobj"), None)
            if noun is not None and noun.lemma_ in ("position", "role", "office"):
                of_prep = next(
                    (c for c in noun.children if c.dep_ == "prep" and c.lower_ == "of"),
                    None,
                )
                if of_prep is not None:
                    of_pobj = next((c for c in of_prep.children if c.dep_ == "pobj"), None)
                    if of_pobj is not None:
                        return _clean_span(of_pobj), of_pobj
            # "elected X to the Board of Directors"
            if noun is not None and noun.lemma_ == "board":
                return "Director", None
            # "promoted to [Role]" — but NOT "promoted FROM [Role] to [Role]",
            # which _ROLE_CHANGE (regex) already extracts as a role_change
            # event; also matching it here would double-count the same
            # transition as a second, spurious "appointment" event.
            if (
                noun is not None
                and noun.pos_ in ("NOUN", "PROPN")
                and verb.lemma_.lower() == "promote"
                and not any(c.dep_ == "prep" and c.lower_ == "from" for c in verb.children)
            ):
                return _clean_span(noun), noun
        # Bare object-predicate role, no preposition at all — by far the most
        # common real-8-K phrasing ("was appointed Chief Financial Officer").
        # Restricted to NOUN/PROPN because this small model also tags some
        # unrelated adjuncts (e.g. "effective" in "...promoted ... effective
        # June 1, 2024") as `oprd`, which are never a job title.
        if child.dep_ == "oprd" and child.pos_ in ("NOUN", "PROPN"):
            return _clean_span(child), child
    if _BOARD_DIRECTOR.search(sent.text):
        return "Director", None
    return None, None


def _find_role(verb, sent) -> str | None:
    return _find_role_and_token(verb, sent)[0]


def _clean_span(token) -> str:
    span = token.doc[token.left_edge.i : token.i + 1]
    return re.sub(r"\s+", " ", span.text).strip(" ,.")


def _find_date(sent, verb, filing_date: date, *, allow_filing_fallback: bool = False) -> date | None:
    dates = [ent for ent in sent.ents if ent.label_ == "DATE"]
    parsed: list[tuple[int, date]] = []
    for ent in dates:
        for month in _MONTHS:
            m = re.search(rf"{month}\s+\d{{1,2}},\s+\d{{4}}", ent.text)
            if m:
                parsed.append((abs(ent.start - verb.i), _parse_date(m.group(0))))
                break
    if len(parsed) == 1:
        return parsed[0][1]
    if len(parsed) > 1:
        parsed.sort(key=lambda row: row[0])
        return parsed[0][1]
    if _TRAILING_IMMEDIATE.search(sent.text):
        return filing_date
    # Explicit calendar date anywhere in the sentence (NER sometimes misses)
    for month in _MONTHS:
        m = re.search(rf"{month}\s+\d{{1,2}},\s+\d{{4}}", sent.text)
        if m:
            return _parse_date(m.group(0))
    if allow_filing_fallback:
        return filing_date
    return None


def _is_step_down(token) -> bool:
    """True for "stepped down" / "will step down" (lemma step + particle down)."""
    if token.lemma_.lower() != "step":
        return False
    return any(c.dep_ == "prt" and c.lower_ == "down" for c in token.children) or bool(
        re.search(r"\bstep(?:ped|s|ping)?\s+down\b", token.sent.text, re.I)
    )


def _extract_appointment_events(
    sent, verb, accession_number: str, cik: int, filing_date: date,
) -> list[EmploymentEvent]:
    role, role_token = _find_role_and_token(verb, sent)
    vacancy = role is None and re.search(
        r"\bvacancy\b|\bnewly[\s-]created\b|\bboard\b", sent.text, re.I
    )
    if role is None and vacancy and _BOARD_DIRECTOR.search(sent.text):
        role = "Director"
    if role is None and not vacancy:
        return []
    effective_date = _find_date(sent, verb, filing_date)
    if effective_date is None:
        # Person+role already resolved — use filing date rather than fail closed
        effective_date = _find_date(sent, verb, filing_date, allow_filing_fallback=True)
    if effective_date is None:
        return []
    role_token_i = role_token.i if role_token is not None else None
    people_tokens: list = []
    for child in verb.children:
        # Exclude the token already consumed as the role source (e.g. an
        # `oprd` role-noun phrase like "Chief Financial Officer" can itself
        # look like a PROPN "name" to _person_name — it isn't a person).
        # Compared by index, not object identity: spaCy's `.children`
        # yields a fresh Token proxy per access, so `is` never matches
        # across separate calls even for the same underlying token.
        if role_token_i is not None and child.i == role_token_i:
            continue
        if child.dep_ in ("dobj", "nsubjpass", "oprd"):
            people_tokens.extend(_expand_conjuncts(child))
        # "joined the Company as CFO" — person is nsubj of join
        if verb.lemma_.lower() in {"join", "hire"} and child.dep_ in ("nsubj",):
            people_tokens.extend(_expand_conjuncts(child))
    events: list[EmploymentEvent] = []
    for token in people_tokens:
        name = _person_name(token)
        if name is None:
            continue
        events.append(EmploymentEvent(
            accession_number, int(cik), "appointment", name,
            role or "Director", effective_date,
        ))
    return events


def _extract_departure_events(
    sent, verb, accession_number: str, cik: int, filing_date: date,
) -> list[EmploymentEvent]:
    if verb.lemma_.lower() == "step" and not _is_step_down(verb):
        return []
    effective_date = _find_date(sent, verb, filing_date)
    if effective_date is None:
        effective_date = _find_date(sent, verb, filing_date, allow_filing_fallback=True)
    if effective_date is None:
        return []
    people_tokens: list = []
    # "[Company] terminated the employment of [Name]" (active voice) -- the
    # departing person is nested inside the object, not the grammatical
    # subject (which is the company/actor doing the terminating). Check this
    # shape first so it doesn't fall through to treating the actor as the
    # person who departed.
    for child in verb.children:
        if child.dep_ == "dobj" and child.lemma_ in _TENURE_NOUNS:
            for grandchild in child.children:
                if grandchild.dep_ == "prep" and grandchild.lower_ == "of":
                    pobj = next((c for c in grandchild.children if c.dep_ == "pobj"), None)
                    if pobj is not None:
                        people_tokens.extend(_expand_conjuncts(pobj))
    if not people_tokens:
        # Passive/intransitive shape: "[Name] resigned/retired/was terminated" --
        # the subject (patient in passive voice) is the departing person.
        for child in verb.children:
            if child.dep_ in ("nsubj", "nsubjpass"):
                people_tokens.extend(_expand_conjuncts(child))
    events: list[EmploymentEvent] = []
    for token in people_tokens:
        name = _person_name(token)
        if name is None:
            continue
        role = None
        if _BOARD_DIRECTOR.search(sent.text):
            role = "Director"
        events.append(EmploymentEvent(
            accession_number, int(cik), "departure", name, role, effective_date,
        ))
    return events


def _possessive_owner_name(noun_token) -> str | None:
    """Name of the person who possesses a departure noun (Jane Doe's resignation)."""
    for child in noun_token.children:
        if child.dep_ in ("poss", "nmod"):
            name = _person_name(child)
            if name is not None:
                return name
            if child.pos_ == "PROPN":
                name = _person_name(child)
                if name is not None:
                    return name
    text_before = noun_token.doc[max(0, noun_token.i - 6) : noun_token.i].text
    m = re.search(
        r"([A-Z][A-Za-z'.-]+(?:\s+[A-Z][A-Za-z'.-]+){1,3})(?:'s|’s)\s*$",
        text_before,
    )
    if m:
        return m.group(1).strip()
    return None


def _role_from_departure_noun(noun_token) -> str | None:
    """"resignation as Chief Financial Officer"."""
    for child in noun_token.children:
        if child.dep_ == "prep" and child.lower_ == "as":
            pobj = next((c for c in child.children if c.dep_ == "pobj"), None)
            if pobj is not None:
                return _clean_span(pobj)
    return None


def _extract_possessive_departure_events(
    sent, accession_number: str, cik: int, filing_date: date,
) -> list[EmploymentEvent]:
    """Nominalised departures: \"Jane Doe's resignation as CFO effective [Date]\"."""
    events: list[EmploymentEvent] = []
    for token in sent:
        if token.pos_ not in ("NOUN", "PROPN"):
            continue
        if token.lemma_.lower() not in _DEPARTURE_NOUNS:
            continue
        name = _possessive_owner_name(token)
        if name is None:
            continue
        effective_date = _find_date(sent, token, filing_date)
        if effective_date is None:
            effective_date = _find_date(
                sent, token, filing_date, allow_filing_fallback=True
            )
        if effective_date is None:
            continue
        events.append(
            EmploymentEvent(
                accession_number,
                int(cik),
                "departure",
                name,
                _role_from_departure_noun(token),
                effective_date,
            )
        )
    return events


def _is_modifier_not_event_clause(token) -> bool:
    """True for \"newly appointed CFO\" style modifiers, not finite event clauses."""
    if token.dep_ in _MODIFIER_DEPS:
        return True
    if token.tag_ in ("VBN", "VBG") and token.dep_ in ("amod", "acl", "oprd"):
        return True
    return False


def _in_section_title_boilerplate(token, section: str) -> bool:
    """Ignore verbs that only appear in the Item 5.02 statutory title line."""
    title = _SECTION_TITLE_SPAN.match(section)
    if not title:
        return False
    # Map character offset approximately via token character span
    return token.idx < title.end()


def parse_item_502(*, accession_number: str, cik: int, filing_date: date,
                   content: str) -> Item502Result:
    text = _text(content)
    if not re.search(r"item\s+5\s*\.\s*02", text, re.I):
        return Item502Result("not_applicable", "item_5_02_absent", ())
    section = _item_502_section(text)
    events: list[EmploymentEvent] = []
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

    doc = _nlp()(section)
    ambiguous_verb_seen = False
    for sent in doc.sents:
        events.extend(
            _extract_possessive_departure_events(
                sent, accession_number, cik, filing_date
            )
        )
        for token in sent:
            if token.pos_ != "VERB":
                continue
            lemma = token.lemma_.lower()
            is_step_down = lemma == "step" and _is_step_down(token)
            is_appointment = lemma in _APPOINTMENT_VERBS
            is_departure = (lemma in _DEPARTURE_VERBS and lemma != "step") or is_step_down
            if not is_appointment and not is_departure:
                continue
            if _is_hypothetical(token):
                continue
            if _is_modifier_not_event_clause(token):
                continue
            if _in_section_title_boilerplate(token, section):
                continue
            if is_departure and not is_appointment:
                found = _extract_departure_events(
                    sent, token, accession_number, cik, filing_date
                )
            elif is_appointment and not is_departure:
                found = _extract_appointment_events(
                    sent, token, accession_number, cik, filing_date
                )
            elif is_step_down:
                found = _extract_departure_events(
                    sent, token, accession_number, cik, filing_date
                )
            else:
                # Overlap (should be rare) — try appointment then departure
                found = _extract_appointment_events(
                    sent, token, accession_number, cik, filing_date
                ) or _extract_departure_events(
                    sent, token, accession_number, cik, filing_date
                )
            if found:
                events.extend(found)
            else:
                ambiguous_verb_seen = True

    if events:
        deduped: dict[tuple, EmploymentEvent] = {}
        for event in events:
            key = (
                event.event_type,
                event.person_name.casefold(),
                event.effective_date,
                (event.role or "").casefold(),
            )
            deduped[key] = event
        events = sorted(
            deduped.values(),
            key=lambda row: (row.effective_date, row.person_name, row.event_type),
        )
        return Item502Result("applicable", "named_employment_event", tuple(events))
    if ambiguous_verb_seen:
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
