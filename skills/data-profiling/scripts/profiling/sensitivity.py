"""Sensitivity tags and masking.

A column is tagged from four signals: its name's words, detectors on its
values, a vote over its values, and whether its part describes people. Contact
details (email, phone) are personal in any part; other personal words count
only in a part that describes people. A part describes people when its column
names carry given-name or birth words, or when a column named for people or
names holds mostly people's names (one field holding a whole name, as a filer
or signer): at least half its distinct sampled values are two to five words of
letters with no legal form or organisation word.
Sensitive personal means GDPR Article 9 special categories, government
identifiers and financial account numbers (operator ruling, 2026-10-05).

Samples written anywhere keep their shape only (`Aaaa Aaaaa`, `999-99-9999`).
"""

from __future__ import annotations

import re

from .identifiers import luhn, mod97_10

# Words in a column name. Personal words count only in a part that describes people.
PERSONAL = {"name", "given", "first", "last", "surname", "middle", "initial", "birth", "birthday", "dob",
            "age", "email", "mail", "phone", "mobile", "address", "street", "zip", "postal", "postcode",
            "latitude", "longitude", "lat", "lon", "lng", "gender", "sex", "title"}
# Personal words whose values identify a person (never a code list); gender or title may be codes.
IDENTITY = {"name", "given", "first", "last", "surname", "middle", "initial", "birth", "birthday", "dob", "email",
            "mail", "phone", "mobile", "address", "street", "zip", "postal", "postcode", "latitude", "longitude",
            "lat", "lon", "lng"}
# Contact words: personal in any part (a contact is a person, whoever they work for).
CONTACT = {"email", "phone", "mobile", "telephone"}  # "mail" alone is post (mail routing)
PERSON_PART = {"given", "surname", "forename", "birth", "birthday", "dob", "middle", "maiden"}
# "first" and "last" mean a person only next to "name": a first address line is not a person.
PERSON_PAIRS = ({"first", "name"}, {"last", "name"})
SENSITIVE = {"ssn", "passport", "national", "tax", "health", "diagnosis", "medical", "religion", "religious",
             "ethnicity", "ethnic", "race", "racial", "union", "biometric", "genetic", "sexual", "orientation",
             "political", "iban", "card", "account"}
# A word that only means "sensitive" next to another word: tax id, card number, account number.
SENSITIVE_PAIRED = {"tax": {"id", "number", "no"}, "card": {"number", "no"}, "account": {"number", "no"},
                    "national": {"id", "number", "no"}, "union": {"member", "membership"}}

# Words that make a name an organisation's: legal forms (written with or without dots) and the common English
# nouns organisations name themselves by. Incomplete across languages by nature; a miss over-masks, never leaks.
ORGANISATION = {"inc", "incorporated", "corp", "corporation", "co", "llc", "llp", "lp", "lllp", "ltd", "limited",
                "plc", "ag", "sa", "se", "nv", "bv", "gmbh", "kg", "kgaa", "mbh", "spa", "srl", "sarl", "sas",
                "ab", "as", "asa", "oy", "oyj", "aps", "pte", "pty", "bhd", "kk", "sro", "spol", "kft", "doo",
                "jsc", "ltda", "sl", "trust", "trustee", "trustees", "fund", "funds", "bank", "holdings",
                "holding", "group", "partners", "partnership", "capital", "management", "advisors", "advisers",
                "associates", "investments", "investment", "securities", "foundation", "university",
                "association", "society", "international", "services", "technologies", "technology", "the", "of",
                "and", "for", "&", "estate", "family", "ventures", "equity", "financial", "insurance", "systems",
                "industries", "energy", "global", "office", "council", "authority", "department", "ministry",
                "municipality", "church", "school", "hospital", "club"}
# A column whose name carries one of these words may hold people's names; its values decide.
NAMING = {"name", "signer", "signatory", "holder", "owner", "filer", "person", "individual", "beneficiary"}
# Words in a column's name that say what else it names (organisations, places, things), so its values are never
# read as people's names: "New York" or "Common Stock" is two capitalised words, like a person's name.
NOT_PEOPLE_COLUMN = {"entity", "firm", "business", "organisation", "organization", "issuer", "institution",
                     "employer", "city", "town", "country", "state", "region", "province", "county", "place",
                     "location", "street", "product", "brand", "category", "item", "security", "instrument",
                     "title", "model", "store"}
# A name column describes people when at least this share of its distinct values are people's names.
PEOPLE = 0.5
# A text that names a person inside it: a title before a name, a name with a middle initial, a
# family's or a person's trust, an estate. On this share of a column's values, the column is personal.
MENTIONS = 0.02
_MENTION = re.compile(r"\b(?:Mr|Mrs|Ms)\.?\s+[A-Z][a-z]+|\bDr\.\s+[A-Z][a-z]+"
                      r"|\b[A-Z][a-z]+\s+[A-Z]\.\s+[A-Z][a-z]+"
                      r"|\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+)?\s+(?:Family|Fam)\s+(?:Trust|Fund|Foundation)\b"
                      r"|\b(?i:estate of)\s+[A-Z]"
                      r"|\b[A-Z][a-z]+\s+(?:Revocable|Irrevocable|Living)\s+Trust\b")
_NAME_WORD = re.compile(r"^[^\W\d_][^\W\d_.'\-]*(?:[.'\-][^\W\d_]*)*\.?$")
_SIGNED = re.compile(r"^/s/\s*", re.I)  # a conformed signature: "/s/ <name>"
_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[A-Za-z]{2,}$")


def words(column: str) -> list[str]:
    """`GivenName` → given, name; `date_of_birth` → date, of, birth."""
    spaced = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", column)
    spaced = re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1 \2", spaced)
    return [w.lower() for w in re.split(r"[^A-Za-z0-9]+", spaced) if w]


def person_part(column_names: list[str]) -> bool:
    """A part describes people when its column names carry personal-name or birth words."""
    found = set()
    for name in column_names:
        said = set(words(name))
        found |= said & PERSON_PART
        found |= {"+".join(sorted(pair)) for pair in PERSON_PAIRS if pair <= said}
    return len(found) >= 2


def _name_words(text: str) -> list[str]:
    return [w for w in re.split(r"[\s,]+", text) if w]


def _bare(word: str) -> str:
    """`S.r.o.,` → `sro`: legal forms are written with and without dots."""
    return word.lower().replace(".", "").strip(",")


def _words_of_a_person(text: str) -> bool:
    found = _name_words(text)
    return (2 <= len(found) <= 5 and all(_NAME_WORD.match(w) for w in found)
            and not any(_bare(w) in ORGANISATION for w in found))


def person_name(value) -> bool:
    """A value shaped like a person's name: two to five words of letters (initials, hyphens and apostrophes
    allowed), no digits and no organisation word. A signed name keeps the words before its first comma
    ("/s/ Ann Cole, Attorney-in-Fact"); a name whose words after the comma are all organisation words
    ("Acme Widgets, Inc.") is an organisation's."""
    if value is None:
        return False
    text = _SIGNED.sub("", str(value).strip())
    head, comma, tail = text.partition(",")
    if not comma:
        return _words_of_a_person(text)
    after = [_bare(w) for w in _name_words(tail) if _bare(w)]
    if after and all(w in ORGANISATION for w in after):
        return False
    return _words_of_a_person(text) or _words_of_a_person(head)


def mentions_people(values: list[str]) -> bool:
    """At least `MENTIONS` of the values name a person inside a text (`_MENTION`)."""
    texts = [v for v in values if isinstance(v, str)]
    return bool(texts) and sum(1 for v in texts if _MENTION.search(v)) >= MENTIONS * len(texts)


def names_people(column: str, values: list[str]) -> bool:
    """A column named for people or names (not for organisations, places or things) whose distinct sampled values
    are mostly people's names."""
    said = set(words(column))
    if not said & NAMING or said & NOT_PEOPLE_COLUMN:
        return False
    distinct = {str(v).strip() for v in values if v is not None and str(v).strip()}
    return bool(distinct) and sum(map(person_name, distinct)) / len(distinct) >= PEOPLE


def _sensitive_word(found: list[str]) -> bool:
    for word in found:
        if word in SENSITIVE_PAIRED:
            if set(found) & SENSITIVE_PAIRED[word]:
                return True
        elif word in SENSITIVE:
            return True
    return False


def value_detectors(values: list[str]) -> dict[str, float]:
    """Share of sampled non-null values each detector accepts."""
    values = [str(v).strip() for v in values if v is not None and str(v).strip()]
    if not values:
        return {}
    digits = [re.sub(r"[ -]", "", v) for v in values]
    return {
        "email": sum(bool(_EMAIL.match(v)) for v in values) / len(values),
        "card_number": sum(13 <= len(d) <= 19 and luhn(d) for d in digits) / len(values),
        "iban": sum(bool(re.match(r"^[A-Z]{2}\d{2}[A-Z0-9]{10,30}$", d)) and mod97_10(d[4:] + d[:4]) for d in digits)
        / len(values),
    }


def tag(column: str, values: list[str], people: bool) -> dict:
    """`none`, `personal` or `sensitive_personal`, with the signals that decided it."""
    found = words(column)
    detected = value_detectors(values)
    signals = []
    if _sensitive_word(found):
        signals.append("name: sensitive word")
    if detected.get("card_number", 0) >= 0.5 or detected.get("iban", 0) >= 0.5:
        signals.append("values: account number with valid check digit")
    if signals:
        return {"sensitivity": "sensitive_personal", "signals": signals}
    if names_people(column, values):
        signals.append("values: people's names")
    elif mentions_people(values):
        signals.append("values: text naming people")
    elif people and set(found) & PERSONAL:
        signals.append("name: personal word in a part describing people")
    if set(found) & CONTACT:
        signals.append("name: contact detail")
    if detected.get("email", 0) >= 0.5:
        signals.append("values: email addresses")
    return {"sensitivity": "personal" if signals else "none", "signals": signals}


def mask(value) -> str | None:
    """Shape only: A for upper case, a for lower case, 9 for a digit; other characters kept."""
    if value is None:
        return None
    return re.sub(r"[0-9]", "9", re.sub(r"[a-z]", "a", re.sub(r"[A-Z]", "A", str(value))))
