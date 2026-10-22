"""Identifier types declared as rules, not code (rebuild priorities ticket 81).

A declaration in `rules/identifiers/<name>.yaml` states an identifier's parts
(each a length and the characters it may hold), its case, whether a run of
one repeated character is a stand-in for none, and its check-digit family.
From it come the format a Dataset Contract checks values with (`<name>`) and
the normalizer matching compares them with (`normalize_identifier@<name>-v<version>`).

The check-digit families are implemented here once, under the names the
data-profiling skill gives them, so a profiling finding becomes a declaration
with no translation. A declaration states its shape as parts, never as a
regular expression, so the vocabulary stays closed (`primitives.py`).
A changed declaration is a new version: its normalizer gets a new name, and
an Identifier Contract pinned to the old name keeps refusing until moved.
"""

from __future__ import annotations

import re
import string
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

# 0-9, then A-Z as 10-35; CUSIP's private-placement characters follow as 36-38.
VALUES = {ch: i for i, ch in enumerate(string.digits + string.ascii_uppercase + "*@#")}


def _luhn_digits(digits: str) -> bool:
    total = 0
    for i, ch in enumerate(reversed(digits)):
        d = int(ch) * (2 if i % 2 else 1)
        total += d - 9 if d > 9 else d
    return total % 10 == 0


def luhn(value: str) -> bool:
    """Luhn mod 10: double every second digit from the right."""
    return value.isdigit() and _luhn_digits(value)


def luhn_letter_values(value: str) -> bool:
    """Luhn over each character's value (A-Z as 10-35): double every second
    value from the right and add the digits of each result."""
    total = 0
    for i, ch in enumerate(reversed(value)):
        d = VALUES[ch] * (2 if i % 2 else 1)
        total += d // 10 + d % 10
    return total % 10 == 0


def luhn_letter_values_from_left(value: str) -> bool:
    """Luhn over each character's value (A-Z as 10-35), doubling every second
    character counted from the left and adding the digits of each result; the
    last character is the check digit, a digit (FIGI's rule)."""
    if not value[-1].isdigit():
        return False
    total = 0
    for i, ch in enumerate(value[:-1]):
        d = VALUES[ch] * (2 if i % 2 else 1)
        total += d // 10 + d % 10
    return (total + int(value[-1])) % 10 == 0


def luhn_letter_digits(value: str) -> bool:
    """Luhn over the digits of each character's value (each letter two digits)."""
    return _luhn_digits("".join(str(VALUES[ch]) for ch in value))


def mod97_10(value: str) -> bool:
    """ISO 7064 mod 97-10: letters read as 10-35; the number mod 97 is 1."""
    return int("".join(str(VALUES[ch]) for ch in value)) % 97 == 1


def mod11_2(value: str) -> bool:
    """ISO 7064 mod 11-2: digits, the last may be X."""
    check = 0
    for ch in value:
        check = (2 * check + (10 if ch == "X" else int(ch))) % 11
    return check == 1


def mod11_10(value: str) -> bool:
    """ISO 7064 mod 11-10 (pure system over digits)."""
    check = 5
    for ch in value:
        check = (((check or 10) * 2) % 11 + int(ch)) % 10
    return check == 1


def mod37_36(value: str) -> bool:
    """ISO 7064 mod 37-36 over 0-9 and A-Z."""
    check = 18
    for ch in value:
        check = (((check or 36) * 2) % 37 + VALUES[ch]) % 36
    return check == 1


_DAMM = (
    (0, 3, 1, 7, 5, 9, 8, 6, 4, 2), (7, 0, 9, 2, 1, 5, 4, 8, 6, 3), (4, 2, 0, 6, 8, 7, 1, 3, 5, 9),
    (1, 7, 5, 0, 9, 8, 3, 4, 2, 6), (6, 1, 2, 3, 0, 4, 5, 9, 7, 8), (3, 6, 7, 4, 2, 0, 9, 5, 8, 1),
    (5, 8, 6, 9, 7, 2, 0, 1, 3, 4), (8, 9, 4, 5, 3, 6, 2, 0, 1, 7), (9, 4, 3, 8, 6, 1, 7, 2, 0, 5),
    (2, 5, 8, 1, 4, 3, 6, 7, 9, 0),
)


def damm(value: str) -> bool:
    interim = 0
    for ch in value:
        interim = _DAMM[interim][int(ch)]
    return interim == 0


# The check-digit families, named as data-profiling names them. Each runs only
# on a value its declaration's parts already accepted.
FAMILIES: dict[str, Callable[[str], bool]] = {
    "mod 97-10": mod97_10,
    "mod 11-2": mod11_2,
    "mod 11-10": mod11_10,
    "mod 37-36": mod37_36,
    "luhn": luhn,
    "luhn over letter values": luhn_letter_values,
    "luhn over letter digits": luhn_letter_digits,
    "luhn over letter values from the left": luhn_letter_values_from_left,
    "damm": damm,
}
_DIGITS, _LETTERS = frozenset(string.digits), frozenset(string.ascii_uppercase)
# The characters each family reads; a declaration whose parts allow any other
# is refused, so a value can never reach a family that cannot read it.
READS = {
    "mod 97-10": _DIGITS | _LETTERS,
    "mod 11-2": _DIGITS | {"X"},
    "mod 11-10": _DIGITS,
    "mod 37-36": _DIGITS | _LETTERS,
    "luhn": _DIGITS,
    "luhn over letter values": _DIGITS | _LETTERS | {"*", "@", "#"},
    "luhn over letter digits": _DIGITS | _LETTERS,
    "luhn over letter values from the left": _DIGITS | _LETTERS,
    "damm": _DIGITS,
}
_CLASSES = {"digits": ("0-9", _DIGITS), "letters": ("A-Z", _LETTERS)}
_KEYS = {"identifier", "version", "description", "parts", "case", "check_digit",
         "refuse_one_repeated_character", "stand_ins"}


class DeclarationError(ValueError):
    """A declaration this build cannot run as written."""


def _characters(part: dict, where: str) -> tuple[str, frozenset]:
    """A part's character class, and the characters it allows."""
    chars = part.get("characters")
    if not isinstance(chars, list) or not chars:
        raise DeclarationError(f"{where}: a part lists the characters it may hold")
    out, allowed = [], set()
    for c in chars:
        if c in _CLASSES:
            out.append(_CLASSES[c][0])
            allowed |= _CLASSES[c][1]
        elif isinstance(c, str) and len(c) == 1:
            out.append(re.escape(c))
            allowed.add(c)
        else:
            raise DeclarationError(f"{where}: a character is digits, letters or one character, not {c!r}")
    return "[" + "".join(out) + "]", frozenset(allowed)


@dataclass(frozen=True)
class IdentifierType:
    name: str
    version: int
    shape: re.Pattern
    upper: bool
    check: Callable[[str], bool] | None
    refuse_runs: bool
    stand_ins: frozenset = frozenset()
    # The check-digit family as profiling names it, and the parts' total length.
    family: str | None = None
    length: int = 0

    @property
    def normalizer_name(self) -> str:
        return f"normalize_identifier@{self.name}-v{self.version}"

    @property
    def checksum_reason(self) -> str:
        """The reason a value failing its check digit is set aside."""
        return f"invalid_{self.name}_checksum"

    def normalize(self, item) -> str:
        from edgar_warehouse.rules.source_engine import apply_record_rules

        return apply_record_rules({
            "action": "prepare_matching_value", "name": self.normalizer_name,
            "value": item, "normalizers": {self.normalizer_name: self.upper},
        })

    def refusal(self, item) -> tuple[str, str | None]:
        """The value as kept, and the reason it is refused (None when it is not)."""
        value = self.normalize(item)
        if (not self.shape.fullmatch(value) or value in self.stand_ins
                or (self.refuse_runs and len(set(value)) == 1)):
            return value, f"invalid_{self.name}"
        if self.check and not self.check(value):
            return value, self.checksum_reason
        return value, None


def declared(body: dict, name: str) -> IdentifierType:
    """One declaration, checked; a declaration this build cannot run is refused."""
    where = f"rules/identifiers/{name}.yaml"
    unknown = set(body) - _KEYS
    if unknown:
        raise DeclarationError(f"{where}: unknown keys {sorted(unknown)}")
    if body.get("identifier") != name:
        raise DeclarationError(f"{where}: `identifier` is the file's name")
    version = body.get("version")
    if type(version) is not int or version < 1:
        raise DeclarationError(f"{where}: `version` is a whole number from 1")
    parts = body.get("parts")
    if not isinstance(parts, list) or not parts:
        raise DeclarationError(f"{where}: `parts` lists the identifier's parts")
    pattern, allowed, total = "", frozenset(), 0
    for part in parts:
        length = part.get("length") if isinstance(part, dict) else None
        if type(length) is not int or length < 1:
            raise DeclarationError(f"{where}: each part has a `length` from 1")
        cls, chars = _characters(part, where)
        pattern += cls + "{%d}" % length
        allowed |= chars
        total += length
    case = body.get("case", "as filed")
    if case not in ("upper", "as filed"):
        raise DeclarationError(f"{where}: `case` is upper or as filed")
    family = body.get("check_digit")
    if family is not None and family not in FAMILIES:
        raise DeclarationError(f"{where}: unknown check-digit family {family!r}; known: {sorted(FAMILIES)}")
    if family is not None and not allowed <= READS[family]:
        raise DeclarationError(f"{where}: {family} cannot read {''.join(sorted(allowed - READS[family]))!r}")
    stand_ins = body.get("stand_ins", [])
    if not isinstance(stand_ins, list) or not all(isinstance(v, str) and v for v in stand_ins):
        raise DeclarationError(f"{where}: `stand_ins` lists the values written for none")
    return IdentifierType(
        name=name,
        version=version,
        shape=re.compile(pattern),
        upper=case == "upper",
        check=FAMILIES[family] if family else None,
        refuse_runs=body.get("refuse_one_repeated_character") is True,
        # Compared as the value is kept (trimmed, and upper-cased when declared so).
        stand_ins=frozenset(v.strip().upper() if case == "upper" else v.strip() for v in stand_ins),
        family=family,
        length=total,
    )


def load(root: Path | None = None) -> dict[str, IdentifierType]:
    """The rules root's declarations (`EDGAR_RULES_ROOT`, read once at import:
    a trial with its own rules folder sets it, since a declaration is a
    format and a normalizer for the whole process, not for one policy)."""
    from edgar_warehouse.rules import files

    return {name: declared(body, name) for name, body in files.identifiers(root).items()}


TYPES = load()
