"""Generic identifier detectors: shape, length and check-digit families.

No list of known identifier types: a column is identifier-shaped when its values
share one length or one shape, and a check-digit family counts only when its pass
rate is at least five times its chance rate: clean at 0.99, and at 0.5 with its
failing values reported as defects.
"""

from __future__ import annotations

import random
import string

BASE36 = {ch: i for i, ch in enumerate(string.digits + string.ascii_uppercase)}
# A letter-value family also reads `*`, `@` and `#` as 36, 37 and 38, as an identifier type
# declares it (data-onboarding REFERENCE.md, "Identifier types").
VALUES = {**BASE36, "*": 36, "@": 37, "#": 38}

# What an identifier column writes for "no value": a written stand-in, compared upper-cased and
# trimmed with its punctuation kept ("N/A" is one; a bare "NA" may be a real code), or a run of
# one repeated 0 or 9 of three or more characters. Left out of shape, check-digit and entity
# tests, and reported to quality, which proposes the engine's placeholder check.
STAND_INS = ("N/A", "#N/A", "NONE", "NULL", "UNKNOWN", "NOT AVAILABLE", "NOT APPLICABLE")


def is_stand_in(value) -> bool:
    text = str(value).strip().upper()
    return text in STAND_INS or (len(text) >= 3 and (set(text) == {"0"} or set(text) == {"9"}))


def stand_in_sql(text: str) -> str:
    """The same test in SQL, over a VARCHAR expression."""
    listed = ", ".join("'" + s.replace("'", "''") + "'" for s in STAND_INS)
    return (f"(upper(trim({text})) IN ({listed}) OR regexp_full_match(trim({text}), '0{{3,}}') "
            f"OR regexp_full_match(trim({text}), '9{{3,}}'))")


def real_value_sql(e: str) -> str:
    """Rows of a column that hold a value: not null, not blank, not a stand-in for none."""
    text = f"CAST({e} AS VARCHAR)"
    return f"{e} IS NOT NULL AND trim({text}) <> '' AND NOT {stand_in_sql(text)}"


def mod97_10(value: str) -> bool:
    """ISO 7064 mod 97-10: letters read as 10-35; the number mod 97 is 1."""
    if len(value) < 3 or not value.isalnum() or not value.isascii():
        return False
    return int("".join(str(BASE36[ch]) for ch in value.upper())) % 97 == 1


def mod11_2(value: str) -> bool:
    """ISO 7064 mod 11-2: digits, last may be X."""
    if len(value) < 2 or not value[:-1].isdigit() or not (value[-1].isdigit() or value[-1] in "Xx"):
        return False
    check = 0
    for ch in value:
        check = (2 * check + (10 if ch in "Xx" else int(ch))) % 11
    return check == 1


def mod11_10(value: str) -> bool:
    """ISO 7064 mod 11-10 (pure system over digits)."""
    if len(value) < 2 or not value.isdigit():
        return False
    check = 5
    for ch in value:
        check = (((check or 10) * 2) % 11 + int(ch)) % 10
    return check == 1


def mod37_36(value: str) -> bool:
    """ISO 7064 mod 37-36 over 0-9 and A-Z."""
    if len(value) < 2 or not value.isalnum() or not value.isascii():
        return False
    check = 18
    for ch in value.upper():
        check = (((check or 36) * 2) % 37 + BASE36[ch]) % 36
    return check == 1


def luhn_letter_values(value: str) -> bool:
    """Luhn over letters and digits, each character read as its value (0-9, A-Z as 10-35, then
    `*@#`): double every second value from the right and add the digits of each result."""
    value = value.upper()
    if len(value) < 2 or any(ch not in VALUES for ch in value):
        return False
    total = 0
    for i, ch in enumerate(reversed(value)):
        d = VALUES[ch] * (2 if i % 2 else 1)
        total += d // 10 + d % 10
    return total % 10 == 0


def luhn_letter_digits(value: str) -> bool:
    """Luhn over the digits of each character's value (A-Z as 10-35, so each letter is two digits)."""
    value = value.upper()
    if len(value) < 2 or any(ch not in VALUES for ch in value) or value.isdigit():
        return False
    return luhn("".join(str(VALUES[ch]) for ch in value))


def luhn(value: str) -> bool:
    """Luhn mod 10: double every second digit from the right."""
    if len(value) < 2 or not value.isdigit():
        return False
    total = 0
    for i, ch in enumerate(reversed(value)):
        d = int(ch) * (2 if i % 2 else 1)
        total += d - 9 if d > 9 else d
    return total % 10 == 0


_DAMM = (
    (0, 3, 1, 7, 5, 9, 8, 6, 4, 2), (7, 0, 9, 2, 1, 5, 4, 8, 6, 3), (4, 2, 0, 6, 8, 7, 1, 3, 5, 9),
    (1, 7, 5, 0, 9, 8, 3, 4, 2, 6), (6, 1, 2, 3, 0, 4, 5, 9, 7, 8), (3, 6, 7, 4, 2, 0, 9, 5, 8, 1),
    (5, 8, 6, 9, 7, 2, 0, 1, 3, 4), (8, 9, 4, 5, 3, 6, 2, 0, 1, 7), (9, 4, 3, 8, 6, 1, 7, 2, 0, 5),
    (2, 5, 8, 1, 4, 3, 6, 7, 9, 0),
)


def damm(value: str) -> bool:
    if len(value) < 2 or not value.isdigit():
        return False
    interim = 0
    for ch in value:
        interim = _DAMM[interim][int(ch)]
    return interim == 0


# family: (validator, chance pass rate for a random value of the right characters)
FAMILIES = {
    "mod 97-10": (mod97_10, 1 / 97),
    "mod 11-2": (mod11_2, 1 / 11),
    "mod 11-10": (mod11_10, 1 / 10),
    "mod 37-36": (mod37_36, 1 / 36),
    "luhn": (luhn, 1 / 10),
    "luhn over letter values": (luhn_letter_values, 1 / 10),
    "luhn over letter digits": (luhn_letter_digits, 1 / 10),
    "damm": (damm, 1 / 10),
}
CHECKED = 20_000  # distinct values tested per column, chosen with a fixed seed
PASS, LIFT = 0.99, 5
# A family passing at least half the values and five times chance is still the column's family:
# no random column reaches that, so the failing values are defects (mistyped or invented
# identifiers, such as an option's made-up issue number on a security id), handed to quality.
DEFECTIVE = 0.5


def check_digits(values: list[str], seed: int = 0) -> dict:
    """Pass rate per family over distinct values, and the family that clears both bars (or None)."""
    values = sorted({str(v).strip() for v in values if v is not None and str(v).strip() and not is_stand_in(v)})
    if len(values) > CHECKED:
        values = random.Random(seed).sample(values, CHECKED)
    if not values:
        return {"family": None, "pass_rate": None, "defective": False, "chance_rate": None, "rates": {}, "tested": 0}
    rates = {name: round(sum(map(test, values)) / len(values), 6) for name, (test, _) in FAMILIES.items()}
    passing = [(rates[n], n) for n, (_, chance) in FAMILIES.items()
               if rates[n] >= DEFECTIVE and rates[n] >= LIFT * chance]
    # The highest pass rate; on a tie the family listed first (plain Luhn over letter-value Luhn on digits).
    order = list(FAMILIES)
    best = max(passing, key=lambda rn: (rn[0], -order.index(rn[1])))[1] if passing else None
    return {"family": best, "pass_rate": rates[best] if best else None,
            "defective": bool(best) and rates[best] < PASS,
            "chance_rate": round(FAMILIES[best][1], 6) if best else None, "rates": rates, "tested": len(values)}


PREFIX = 0.9  # a number issued under a prefix: one text before its first separator on 90% of values


def shape_test(profile: dict) -> dict | None:
    """Which shape test a column passes as an identifier, with its share; None if none.

    One length, or one character shape, on 99% of values; or one pattern (each run of
    one character class collapsed, so `X-1234` and `X-12` are both `A-9`) holding a
    separator on 99% of text values, one prefix before that separator on 90%, and not
    a date or a time (`3/4/2022`, `9:30`, ranges like `12-4000` fail the prefix)."""
    from .profile import SEPARATORS
    if profile["length_share"] >= 0.99:
        return {"test": "one length", "share": profile["length_share"]}
    if profile["shape_share"] >= 0.99:
        return {"test": "one shape", "share": profile["shape_share"]}
    if profile.get("type") == "VARCHAR" and profile.get("pattern_share", 0.0) >= 0.99 \
            and any(s in (profile.get("pattern") or "") for s in SEPARATORS) \
            and profile.get("prefix_share", 0.0) >= PREFIX and profile.get("pattern_temporal_share", 1.0) < 0.5:
        return {"test": "one pattern under one prefix", "share": profile["pattern_share"],
                "prefix_share": profile["prefix_share"]}
    return None


def identifier_shaped(profile: dict) -> bool:
    """One length, shape or prefixed pattern for (nearly) every value, and more than a handful of values."""
    from .profile import is_temporal
    if not profile["non_null"] or profile["structure"] or profile.get("tokens", 0) > 1.0 or is_temporal(profile):
        return False
    return profile["distinct"] >= 20 and shape_test(profile) is not None and (profile["min_length"] or 0) >= 3


def dense_sequence(profile: dict) -> bool:
    """An integer column whose values fill their range: a local surrogate, not an issued identifier."""
    try:
        low, high = int(profile["min"]), int(profile["max"])
    except (KeyError, TypeError, ValueError):
        return False
    return profile["unique"] == 1.0 and high - low + 1 <= profile["distinct"] * 1.05


def local_counter(profile: dict) -> bool:
    """An integer column filling its range: a local counter, never an issued identifier."""
    from .profile import is_integer
    return is_integer(profile) and dense_sequence(profile)
