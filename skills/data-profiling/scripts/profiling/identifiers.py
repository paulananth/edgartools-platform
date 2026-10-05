"""Generic identifier detectors: shape, length and check-digit families.

No list of known identifier types: a column is identifier-shaped when its values
share one length or one shape, and a check-digit family counts only when its pass
rate is at least 0.99 and at least five times its chance rate.
"""

from __future__ import annotations

import random
import string

_BASE36 = {ch: i for i, ch in enumerate(string.digits + string.ascii_uppercase)}


def mod97_10(value: str) -> bool:
    """ISO 7064 mod 97-10: letters read as 10-35; the number mod 97 is 1."""
    if len(value) < 3 or not value.isalnum() or not value.isascii():
        return False
    return int("".join(str(_BASE36[ch]) for ch in value.upper())) % 97 == 1


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
        check = (((check or 36) * 2) % 37 + _BASE36[ch]) % 36
    return check == 1


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
    "damm": (damm, 1 / 10),
}
CHECKED = 20_000  # distinct values tested per column, chosen with a fixed seed
PASS, LIFT = 0.99, 5


def check_digits(values: list[str], seed: int = 0) -> dict:
    """Pass rate per family over distinct values, and the family that clears both bars (or None)."""
    values = sorted({str(v).strip() for v in values if v is not None and str(v).strip()})
    if len(values) > CHECKED:
        values = random.Random(seed).sample(values, CHECKED)
    if not values:
        return {"family": None, "rates": {}, "tested": 0}
    rates = {name: round(sum(map(test, values)) / len(values), 6) for name, (test, _) in FAMILIES.items()}
    passing = [(rates[n], n) for n, (_, chance) in FAMILIES.items() if rates[n] >= PASS and rates[n] >= LIFT * chance]
    best = max(passing)[1] if passing else None
    return {"family": best, "pass_rate": rates[best] if best else None,
            "chance_rate": round(FAMILIES[best][1], 6) if best else None, "rates": rates, "tested": len(values)}


def identifier_shaped(profile: dict) -> bool:
    """One length or one shape for (nearly) every value, and more than a handful of values."""
    if not profile["non_null"] or profile["structure"] or profile.get("tokens", 0) > 1.0:
        return False
    return profile["distinct"] >= 20 and max(profile["shape_share"], profile["length_share"]) >= 0.99 \
        and (profile["min_length"] or 0) >= 3


def dense_sequence(profile: dict) -> bool:
    """An integer column whose values fill their range: a local surrogate, not an issued identifier."""
    try:
        low, high = int(profile["min"]), int(profile["max"])
    except (KeyError, TypeError, ValueError):
        return False
    return profile["unique"] == 1.0 and high - low + 1 <= profile["distinct"] * 1.05
