"""Sensitivity tags and masking.

A column is tagged from four signals: its name's words, detectors on its
values, a vote over its values, and whether its part describes people.
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
PERSON_PART = {"given", "first", "surname", "last", "birth", "birthday", "dob", "middle"}
SENSITIVE = {"ssn", "passport", "national", "tax", "health", "diagnosis", "medical", "religion", "religious",
             "ethnicity", "ethnic", "race", "racial", "union", "biometric", "genetic", "sexual", "orientation",
             "political", "iban", "card", "account"}
# A word that only means "sensitive" next to another word: tax id, card number, account number.
SENSITIVE_PAIRED = {"tax": {"id", "number", "no"}, "card": {"number", "no"}, "account": {"number", "no"},
                    "national": {"id", "number", "no"}, "union": {"member", "membership"}}

_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[A-Za-z]{2,}$")


def words(column: str) -> list[str]:
    """`GivenName` → given, name; `date_of_birth` → date, of, birth."""
    spaced = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", column)
    spaced = re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1 \2", spaced)
    return [w.lower() for w in re.split(r"[^A-Za-z0-9]+", spaced) if w]


def person_part(column_names: list[str]) -> bool:
    """A part describes people when its column names carry personal-name or birth words."""
    found = {w for name in column_names for w in words(name)} & PERSON_PART
    return len(found) >= 2


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
    if people and set(found) & PERSONAL:
        signals.append("name: personal word in a part describing people")
    if people and detected.get("email", 0) >= 0.5:
        signals.append("values: email addresses in a part describing people")
    return {"sensitivity": "personal" if signals else "none", "signals": signals}


def mask(value) -> str | None:
    """Shape only: A for upper case, a for lower case, 9 for a digit; other characters kept."""
    if value is None:
        return None
    return re.sub(r"[0-9]", "9", re.sub(r"[a-z]", "a", re.sub(r"[A-Z]", "A", str(value))))
