"""Person-name normalizer for the Person consumer contract (``person-name@v2``).

Parses a natural person's name into surname, given name, middle names and
suffixes, and decides whether a free-text name field is a person name at all.
It is the primitive under ticket 20's Tier B key -- same issuer identity AND
surname + given name + middle initial AND no generational-suffix conflict --
and under the policy language's ``name_shape`` primitive
(docs/specs/mdm/policy-language.md). Pure functions, no I/O, no network.

``v1`` is research 17's normalizer (``.scratch/person-consumer-contract/
research/17-common.py``), the one research 21 measured. ``v2`` repairs the
three defects research 21 found in it (Person Consumer Contract ticket 25),
none of which touches the key:

1. **Multi-word surnames.** v1 took one token as the surname, so a particle
   (``di``, ``de``, ``van`` ...) became the given name: the Zegna brothers
   ("Zegna di Monte Rubello Edoardo" / "... Angelo") both parsed to
   ``ZEGNA|DI|M``, the key's only false merge against Form 3/4/5's 11
   same-issuer homonym CIK pairs. A particle now joins the surname.
2. **``V`` is not a suffix.** v1's suffix set carried ``V``, so a middle
   initial V ("CRAWFORD MATTHEW V", "Mark V. Anquillare") was discarded --
   241 Form 3/4/5 and 7 8-K records. The generational set is ticket 20's own
   ``JR``/``SR``/``II``/``III``/``IV``.
3. **Eligibility.** ``DATE`` and ``BANK`` were missing from the non-person
   vocabulary, so "Effective Date" and "Manufacturers Bank" reached a tier.

Two input forms, because SEC sources use two:

- **conformed** -- EDGAR's ``LAST FIRST MIDDLE [SUFFIX]`` (Form 3/4/5
  ``rptOwnerName``, read from silver ``owner_name_raw``);
- **western** -- free text ``First Middle Last [Suffix]`` (8-K Item 5.02
  ``person_name``, DEF 14A ``exec_name``).

Eligibility: ``is_person_name_candidate`` is for the **free-text** sources
only. A conformed Form 3/4/5 name is already classified person-or-entity by
rule C-J (docs/specs/person/consumer.md) before it reaches this module;
``parse_conformed(...).shape`` says only that it parses, not that it is a
person ("BLACKROCK INC" has shape).

Known limits, identical in v1 unless noted:

- A conformed surname of several tokens *without* a particle
  ("SMITH JONES MARY") cannot be told from surname + given + middle. A
  hyphenated one loses its hyphen in normalization ("SMITH-JONES MARY" ->
  ``SMITH`` / ``JONES``), so it does not match western "Mary Smith-Jones".
- With a particle and four or more tokens the split is a reading
  ("ZEGNA DI MONTE" / "RUBELLO" / "EDOARDO" -- not the family's own, but the
  brothers no longer share a key; v2 only).
- A hyphenated given name splits into given + middle ("UANG DU-TSUEN" ->
  ``DU`` / ``TSUEN``) -- consistently in both forms, so the key still matches.
- Vietnamese "Van" as a middle name ("Thanh Van Nguyen") reads as a particle
  in western form (surname ``VAN NGUYEN``) but not in conformed
  ("NGUYEN THANH VAN"); none occurs in research 21's census (v2 only).
- Dotted credentials split before suffix matching ("M.D." -> ``M`` ``D``).
- An honorific followed by a particle surname with no given name
  ("Mr. Ploos van Amstel") reads the first surname token as a given name.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

NORMALIZER_VERSION = "person-name@v2"

# Ticket 20 Q3 point 3: the generational-suffix veto uses exactly these.
GENERATIONAL_SUFFIXES: frozenset[str] = frozenset({"JR", "SR", "II", "III", "IV"})

# Professional credentials: stripped from the name core, never a veto.
CREDENTIAL_SUFFIXES: frozenset[str] = frozenset({
    "ESQ", "CFA", "CPA", "CFP", "PHD", "MD", "JD", "MBA", "DDS", "PE",
    "RIA", "CIMA", "AIF", "CLU", "CHFC", "CIC", "PPC",
})

SUFFIXES: frozenset[str] = GENERATIONAL_SUFFIXES | CREDENTIAL_SUFFIXES

# Surname particles (research 21 F7b's list, plus the common compounds). One
# *following* a surname token joins it ("GOMIDE DE FARIA", "SANTOS DO CARMO").
SURNAME_PARTICLES: frozenset[str] = frozenset({
    "DA", "DAL", "DAS", "DE", "DEL", "DELLA", "DEN", "DER", "DI", "DO", "DOS",
    "DU", "LA", "LE", "TER", "VAN", "VON",
})

# Particles that are also common standalone surnames in SEC filings (Indian
# Das, Chinese Du, Vietnamese Le and Do). They join a surname only mid-name;
# they never *start* one, and never start a compound given name -- "DAS
# MANUVIR", "DU WEI", "LE TRUC THANH" are surname + given name. DO is not a
# credential for the same reason (the Vietnamese surname, "DO CUONG V").
STANDALONE_SURNAMES: frozenset[str] = frozenset({"DAS", "DO", "DU", "LE"})
_LEADING_PARTICLES: frozenset[str] = SURNAME_PARTICLES - STANDALONE_SURNAMES

# Western-form titles, dropped before parsing. GENERAL is also in
# NON_PERSON_TOKENS, which wins in is_person_name_candidate ("General John
# Smith" is ineligible) -- the safe side, as research 01 had it.
HONORIFICS: frozenset[str] = frozenset({
    "MR", "MRS", "MS", "MISS", "DR", "PROF", "SIR", "HON", "REV", "SPEAKER",
    "SENATOR", "GOVERNOR", "GENERAL", "ADMIRAL",
})

# Titles dropped from a *conformed* name too ("Akbari Dr. Homaira",
# "PRICE BILLY L JR DR"). Deliberately narrower than HONORIFICS: HON, MISS,
# GENERAL and the rest are real surnames/given names in EDGAR's conformed
# form. The Mastering Policy prototype's `person_suffix` (rule C-J's
# name_shape list) carries MR/MRS/MS/DR as suffixes; here they are titles.
# Same tokens, same effect on the key (removed from the core); reconcile the
# two declarations when the Person policy declares this normalizer.
CONFORMED_HONORIFICS: frozenset[str] = frozenset({"MR", "MRS", "MS", "DR"})

# ADV Schedule A/B's "no middle name" placeholder.
_DROP_TOKENS: frozenset[str] = frozenset({"NMN"})

# Research 01's role vocabulary: a free-text name field containing any of
# these is role or entity text, not a person's name. DATE and BANK added in
# v2 (ticket 25). Note DATE is also a real surname ("Rajeev Date"): such a
# name is deferred to review, never mis-bound -- ineligible is the safe side.
NON_PERSON_TOKENS: frozenset[str] = frozenset({
    "CHIEF", "OFFICER", "PRESIDENT", "CHAIRMAN", "CHAIR", "DIRECTOR",
    "DIRECTORS", "EXECUTIVE", "FINANCIAL", "OPERATING", "VICE", "SENIOR",
    "GENERAL", "COUNSEL", "SECRETARY", "TREASURER", "COMMITTEE", "COMMITTEES",
    "BOARD", "COMPANY", "CORPORATION", "INC", "LLC", "LTD", "CORP", "PLAN",
    "EQUITY", "INCENTIVE", "FORMER", "INTERIM", "MEMBER", "EMPLOYMENT",
    "AGREEMENT", "COMPENSATORY", "ARRANGEMENT", "CONTROLLER", "ACCOUNTING",
    "MANAGER", "MANAGING", "GROUP", "PARTNERS", "CAPITAL", "FUND", "TRUST",
    "HOLDINGS", "AND", "OF", "THE", "HIS", "HER", "PREVIOUS", "CEO", "CFO",
    "COO", "CTO", "EVP", "SVP", "VP", "OFFICERS", "LEADERSHIP", "SEC",
    "DATE", "BANK",
})

_PUNCTUATION = re.compile(r"[.,;:/()'\"\-]")
_WHITESPACE = re.compile(r"\s+")
_ALPHA = re.compile(r"[A-Z]+")
_MIN_TOKENS = 2
_MAX_TOKENS = 5


@dataclass(frozen=True)
class PersonName:
    """One parsed name. ``last`` may hold several tokens ("DE LA HOYA"),
    ``first`` may hold two ("LA VONDA"); ``suffixes`` holds generational and
    credential tokens, sorted; ``shape`` is research 17's person-name shape
    (surname and given name present, 2-5 alphabetic core tokens)."""

    last: str
    first: str
    middle: tuple[str, ...]
    suffixes: tuple[str, ...]
    shape: bool

    @property
    def generational(self) -> frozenset[str]:
        return frozenset(s for s in self.suffixes if s in GENERATIONAL_SUFFIXES)

    @property
    def middle_initial(self) -> str:
        return self.middle[0][0] if self.middle else ""

    @property
    def key_mi(self) -> str:
        """Ticket 20's name component: surname | given name | middle initial."""
        return f"{self.last}|{self.first}|{self.middle_initial}"


def normalize_text(name: str | None) -> str:
    """Research 18's ``norm_name``: upper case, ``&`` -> ``AND``, punctuation
    to spaces, whitespace collapsed."""
    s = (name or "").upper().replace("&", " AND ")
    s = _PUNCTUATION.sub(" ", s)
    return _WHITESPACE.sub(" ", s).strip()


def _tokens(name: str | None) -> list[str]:
    return [t for t in normalize_text(name).split(" ") if t and t not in _DROP_TOKENS]


def _split_suffixes(tokens: list[str]) -> tuple[list[str], tuple[str, ...]]:
    core = [t for t in tokens if t not in SUFFIXES]
    suffixes = tuple(sorted({t for t in tokens if t in SUFFIXES}))
    return core, suffixes


def _given(tokens: list[str]) -> tuple[str, tuple[str, ...]]:
    """Given name and middle names from the non-surname tokens. A leading
    particle joins the next token ("LA VONDA", and the hyphenated "DI ANN" /
    "DA WAI" after normalization), in both input forms, so the conformed and
    western spellings of one name produce one key."""
    if len(tokens) >= 2 and tokens[0] in _LEADING_PARTICLES:
        tokens = [f"{tokens[0]} {tokens[1]}", *tokens[2:]]
    return (tokens[0] if tokens else ""), tuple(tokens[1:])


def _shape(core: list[str], last: str, first: str) -> bool:
    return (
        bool(last and first)
        and _MIN_TOKENS <= len(core) <= _MAX_TOKENS
        and all(_ALPHA.fullmatch(t) for t in core)
    )


def parse_conformed(name: str | None) -> PersonName:
    """EDGAR ``LAST FIRST MIDDLE [SUFFIX]``.

    The surname is the first token, extended through any particle run and the
    token that follows it, only while a token still remains after that
    extension to be the given name -- so "WILLIAMS LA VONDA" keeps the
    particle-led given name ``LA VONDA``. With a fourth token the reading is
    genuinely ambiguous ("WILLIAMS LA VONDA MAE" parses surname
    ``WILLIAMS LA VONDA``); see the module's known limit.
    """
    tokens = [t for t in _tokens(name) if t not in CONFORMED_HONORIFICS]
    core, suffixes = _split_suffixes(tokens)
    n = len(core)
    end = 0  # exclusive end of the surname
    while end < n and core[end] in _LEADING_PARTICLES:
        end += 1
    end += 1  # the surname's head token
    if end >= n >= 2:  # the leading run left no given name: "DE SILVA"
        end = 1
    while end < n:
        j = end
        while j < n and core[j] in SURNAME_PARTICLES:
            j += 1
        if j == end or j + 1 >= n:  # no particle here, or nothing left for a given name
            break
        end = j + 1
    end = min(end, n)
    last = " ".join(core[:end])
    first, middle = _given(core[end:])
    return PersonName(last, first, middle, suffixes, _shape(core, last, first))


def parse_western(name: str | None) -> PersonName:
    """Free text ``First Middle Last [Suffix]``, honorifics dropped.

    The surname is the last token, extended leftward over the particles that
    precede it. A leading particle that is not part of the surname joins the
    given name ("La Vonda Williams" -> given ``LA VONDA``).
    """
    tokens = [t for t in _tokens(name) if t not in HONORIFICS]
    core, suffixes = _split_suffixes(tokens)
    n = len(core)
    if n == 0:
        return PersonName("", "", (), suffixes, False)
    start = n - 1  # inclusive start of the surname
    while start > 0 and core[start - 1] in SURNAME_PARTICLES:
        start -= 1
    last = " ".join(core[start:])
    first, middle = _given(core[:start])
    return PersonName(last, first, middle, suffixes, _shape(core, last, first))


def is_person_name_candidate(name: str | None) -> bool:
    """A **free-text** name field (8-K, DEF 14A) that may name a person: no
    role or entity vocabulary, and a parsable western shape. Research 01's
    plausibility test plus the two tokens research 21 found missing. Not for
    conformed Form 3/4/5 names -- those are classified by rule C-J."""
    tokens = set(normalize_text(name).split(" "))
    if tokens & NON_PERSON_TOKENS:
        return False
    return parse_western(name).shape
