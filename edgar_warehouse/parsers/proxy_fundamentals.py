"""DEF 14A proxy parser adapter — extracts executive compensation records.

Backed by edgartools' ``extract_summary_compensation`` DOM-based extractor.
Writes to ``sec_executive_record`` in the fundamentals silver namespace.

Architecture note
-----------------
This parser fits the standard per-filing dispatch via ``get_parser()``.
The ``content`` argument is the raw HTML of the primary DEF 14A document.

Person identity and tenure are NOT written to silver — they are computed
downstream by MDM's ``_derive_employed_by`` and stored on the EMPLOYED_BY
relationship instance, not denormalised to silver.
"""

from __future__ import annotations

import dataclasses
import re
from typing import Any

PARSER_NAME = "proxy_fundamentals_v1"
PARSER_VERSION = "3"

# Standardised role codes inferred from raw title strings
_ROLE_MAP = {
    "chief executive officer": "CEO",
    "president and chief executive officer": "CEO",
    "co-chief executive officer": "Co-CEO",
    "chief financial officer": "CFO",
    "chief operating officer": "COO",
    "chief technology officer": "CTO",
    "chief legal officer": "CLO",
    "chief accounting officer": "CAO",
    "general counsel": "General Counsel",
    "executive vice president": "EVP",
    "senior vice president": "SVP",
    "vice president": "VP",
    "principal executive officer": "PEO",
    "principal financial officer": "PFO",
    "executive chairman": "Executive Chairman",
    "chairman": "Chairman",
    "president": "President",
}


def _infer_role(title: str | None) -> str | None:
    """Map a raw proxy title string to a standardised role code."""
    if not title:
        return None
    lower = title.lower().strip()
    for phrase, code in _ROLE_MAP.items():
        if phrase in lower:
            return code
    return None


# --- Name repair -------------------------------------------------------
#
# edgartools' ``extract_summary_compensation`` walks the Summary Compensation
# Table one row per (executive, fiscal year) and re-reads the name column on
# every row. A Summary Compensation Table puts the executive's name on the
# first row of the block and wraps the principal position over the *following*
# rows of that same column, so those continuation lines are read as names and
# carried forward for the rest of the block. The result is that role text lands
# in ``exec_name``. Repaired here rather than upstream because edgartools is a
# pinned PyPI dependency; the fix is a pure post-pass over what it returns.

# Two vocabularies, deliberately separate, overlapping in about 23 entries.
# This one is the *veto* set: any of these anywhere in a candidate name
# disqualifies it. It therefore also carries business-unit nouns that never
# open a title. ``_TITLE_STARTS`` below is the *cut* set: where a title begins
# inside a joined cell, so it carries abbreviations and opening words instead.
#
# Only the cut set is load-bearing for a word in both. ``_split_name_from_title``
# breaks at the first cut word, so every token that reaches the veto check has
# already failed the cut test: the ~23 shared entries can never fire as a veto,
# and the veto's effective vocabulary is the business-unit nouns below. A new
# position word therefore belongs in ``_TITLE_STARTS``. The shared entries are
# kept as cover in case that order ever changes.
_TITLE_WORDS = frozenset(
    {
        "officer",
        "president",
        "chairman",
        "chairwoman",
        "chairperson",
        "chair",
        "counsel",
        "treasurer",
        "secretary",
        "controller",
        "principal",
        "partner",
        "director",
        "manager",
        "head",
        "founder",
        "executive",
        "vice",
        "senior",
        "former",
        "interim",
        "acting",
        "board",
        "operating",
        "financial",
        "accounting",
        "technology",
        "marketing",
        "revenue",
        "administrative",
        # Business-unit words. A name column sometimes holds a unit rather
        # than a person ("Retail Banking Division Manager", "Marketing
        # Services", "Director of Wholesale Banking" — all sampled from real
        # proxies). None of these is a surname.
        "banking",
        "division",
        "services",
        "wholesale",
        "retail",
        "department",
        "segment",
        "lending",
        "brokerage",
        "insurance",
    }
)

# A reference marker on a name cell: "Yoor,(1)", "Smith*", "Smith (2)",
# "Smith†", "Riggsbee (⁸)", "Robuck (6, 7)". Stripped from the name only; the
# extractor already handles markers inside dollar cells.
#
# Matched *anywhere* in the cell, not only at its end, because a marker also
# lands between the name and its position ("Jason Dies(1)Interim", "Stephanie
# Williams (10)VP and") — 462 rows of the bronze re-parse kept one (ticket 26).
# Only digits, single lowercase letters and superscripts count, so a
# parenthesised nickname ("Robert (Bob) Smith") is left alone.
_SUPERSCRIPT_DIGITS = "⁰¹²³⁴⁵⁶⁷⁸⁹"
_MARKER_ITEM = rf"(?:\d+|[a-z]|[{_SUPERSCRIPT_DIGITS}]+)"
_NAME_MARKER_RE = re.compile(
    rf"\(\s*{_MARKER_ITEM}(?:\s*[,;]\s*{_MARKER_ITEM})*\s*\)"
    rf"|[{_SUPERSCRIPT_DIGITS}]+"
    r"|[*†‡§¶]+",
    re.IGNORECASE,
)

# The first half of a position, cut at the name/title boundary: "Chi-Foon Chan
# Co-" (of "Co-CEO"), "Lori Bisson -" (of "- Chief ..."), and the no-space
# variant "Aart J. de GeusCo-". 128 rows kept one (ticket 26). Anchored at the
# end, so "Co-Founder and" — a cell that is position text throughout — and a
# hyphenated given name are both untouched.
_TRAILING_FRAGMENT_RE = re.compile(r"(?:\s+|(?<=[a-z]))[Cc]o-\s*$|\s+-\s*$")

# ASCII-only by design. A space-separated accented name is unaffected, because
# the returned name is sliced from the original cell rather than rebuilt from
# tokens, so "Deirdre O’Brien" and "José Ramírez" survive intact. The gap is
# the no-separator layout below: "DupontéPresident" has no ASCII lower-to-upper
# boundary, so it is read as title text and deferred rather than split. That is
# the safe direction — deferring a name beats inventing one — but it is a known
# limitation for non-English names in that one layout.
_NAME_TOKEN_RE = re.compile(r"[A-Za-z][A-Za-z'’\-\.]*")

# The *cut* set (see ``_TITLE_WORDS`` above for the veto set they overlap).
# Where a principal position starts inside a name cell: real Summary
# Compensation Tables run the two together in one cell ("Luca Maestri Senior
# Vice President"), so the name ends where one of these begins.
_TITLE_STARTS = (
    "chief",
    "president",
    "vice",
    "senior",
    "executive",
    "chairman",
    "chairwoman",
    "chairperson",
    "chair",
    "general",
    "principal",
    "interim",
    "acting",
    "former",
    "head",
    "founder",
    "managing",
    "deputy",
    "corporate",
    "group",
    "global",
    "treasurer",
    "secretary",
    "controller",
    "counsel",
    "evp",
    "svp",
    # 167 rows of the bronze re-parse kept these after a name (ticket 26).
    # "v.p" covers "V.P." and "V.P.-Manufacturing" alike, because
    # ``_is_title_word`` strips the trailing dot from each hyphen part.
    "vp",
    "v.p",
    "sevp",
    "ceo",
    "cfo",
    "coo",
    "cto",
    "board",
    "officer",
    "director",
    "manager",
    "partner",
    "cofounder",
)

# Real cells also run the two together with no space at all
# ("Andreas G. FrankExecutive Vice President", "Martin RaffieldSVP Operations"),
# so a lower-to-upper boundary immediately before a position word splits too.
#
# Deliberately case *sensitive*, matching only the Capitalised and UPPERCASE
# forms. A case-insensitive version splits ordinary surnames at their own
# letters — "Franco" at "co", "Whitehead" at "head" — which would invent
# people out of halves of real names.
#
# Each form is escaped: "v.p" is the first entry carrying a metacharacter, and
# an unescaped dot is a wildcard that would split "John SmithVIP" into a name
# and a title.
_CAMEL_TITLE_RE = re.compile(
    r"(?<=[a-z])(?=(?:"
    + "|".join(
        sorted(
            {
                re.escape(form)
                for word in _TITLE_STARTS
                for form in (word.capitalize(), word.upper())
            },
            key=len,
            reverse=True,
        )
    )
    + r")\b)"
)


def _strip_name_markers(cell: str) -> str:
    """Remove footnote/reference markers from a name cell, wherever they sit.

    Each marker becomes a space, so a marker glued to the position that follows
    it ("Jason Dies(1)Interim") leaves the two separable rather than fused.
    """
    text = _NAME_MARKER_RE.sub(" ", cell.strip())
    return re.sub(r"\s+", " ", text).strip().rstrip(",").strip()


def _cut_trailing_fragment(cell: str) -> tuple[str, str]:
    """Split off a position's first half left at the end of a name cell."""
    match = _TRAILING_FRAGMENT_RE.search(cell)
    if not match:
        return cell, ""
    return cell[: match.start()].strip(), cell[match.start() :].strip()


def _is_title_word(token: str, vocabulary: frozenset[str] | tuple[str, ...]) -> bool:
    """True when a token, or any hyphen-separated part of one, is position text.

    Each part is stripped of its own punctuation, so one "v.p" entry covers
    both "V.P." and the hyphen-glued "V.P.-Manufacturing".
    """
    bare = token.lower().strip(".'’-")
    if bare in vocabulary:
        return True
    return any(
        stripped and stripped in vocabulary
        for part in bare.split("-")
        if (stripped := part.strip(".'’"))
    )


def _split_name_from_title(cell: str) -> tuple[str | None, str]:
    """Split a name-column cell into (person name, trailing title text).

    Two layouts occur in real Summary Compensation Tables and both are handled
    here. The name and the principal position may share one cell — "Luca
    Maestri Senior Vice President" — in which case the name ends where the
    position begins. Or the position wraps onto the *following* rows of the
    same column — "Chairman of the" / "Board and Chief" — in which case the
    cell is all title and carries no name at all.

    Returns ``(None, text)`` for a cell that is title text only. A name needs
    at least two tokens before the position starts, so a cell whose second
    token already begins the position ("Andrew Chief Bearheart") is read as
    title text; that costs a rare real surname and is the safe direction,
    since inventing a person is worse than deferring one.

    The cell is prepared in a fixed order, and the order is the rule: footnote
    markers go first, because one sitting between the name and its position
    hides the boundary the next two steps look for; then the no-separator
    split; then a trailing position fragment, which is title text and is
    returned as such.
    """
    cell = _strip_name_markers(cell)
    cell = _CAMEL_TITLE_RE.sub(" ", cell.strip())
    cell, fragment = _cut_trailing_fragment(cell)

    def _title_only() -> tuple[None, str]:
        return None, " ".join(part for part in (cell.strip(), fragment) if part)

    tokens = _NAME_TOKEN_RE.findall(cell)
    if not tokens:
        return _title_only()

    cut = len(tokens)
    for index, token in enumerate(tokens):
        if _is_title_word(token, _TITLE_STARTS):
            cut = index
            break

    if cut < 2:
        return _title_only()

    # A cut can still leave position text in front of it ("Marketing Services",
    # "Director of Wholesale Banking"). A person's name carries no position
    # vocabulary at all.
    if any(_is_title_word(token, _TITLE_WORDS) for token in tokens[:cut]):
        return _title_only()

    name_tokens = tokens[:cut]
    # Rebuild from the original cell so punctuation and spacing survive.
    name = cell
    if cut < len(tokens):
        marker = tokens[cut]
        position = _find_token_start(cell, marker, name_tokens)
        if position > 0:
            name, trailing = cell[:position].strip(), cell[position:].strip()
        else:
            trailing = ""
    else:
        trailing = ""
    # A cut at the position word can leave the separator that introduced it
    # ("Walter Klemp - Executive Chair"), which is punctuation, never a name.
    name = name.strip().rstrip(",-–—:;/|").strip()
    if len(_NAME_TOKEN_RE.findall(name)) < 2:
        return _title_only()
    return name, " ".join(part for part in (trailing, fragment) if part)


def _find_token_start(cell: str, marker: str, preceding: list[str]) -> int:
    """Character offset of ``marker`` in ``cell``, skipping earlier tokens."""
    offset = 0
    for token in preceding:
        found = cell.find(token, offset)
        if found == -1:
            return -1
        offset = found + len(token)
    return cell.find(marker, offset)


def _repair_entry_names(entries: list[Any]) -> list[Any]:
    """Restore each row's executive name, dropping rows with no owner.

    Rows whose name column holds a title continuation inherit the name of the
    executive whose block they belong to, and their text is appended to that
    executive's title so a wrapped position reassembles. A continuation that
    precedes any name has no attributable person, so it is dropped rather than
    published under role text.
    """
    repaired: list[Any] = []
    current_name: str | None = None
    current_title = ""
    owner_indexes: list[int] = []

    def _retitle(title: str) -> None:
        for index in owner_indexes:
            repaired[index] = dataclasses.replace(repaired[index], title=title)

    for entry in entries:
        raw_name = str(getattr(entry, "name", "") or "")
        raw_title = str(getattr(entry, "title", "") or "").strip()
        name, trailing = _split_name_from_title(raw_name)

        if name is not None:
            current_name = name
            current_title = " ".join(part for part in (trailing, raw_title) if part).strip()
            owner_indexes = [len(repaired)]
            repaired.append(dataclasses.replace(entry, name=name, title=current_title))
            continue

        if current_name is None:
            # Title text before any executive: nothing to attribute it to.
            continue

        # A continuation line: it belongs to the title of the executive whose
        # block this row is in, never to the name.
        if trailing and trailing.lower() not in current_title.lower():
            current_title = f"{current_title} {trailing}".strip()
            _retitle(current_title)

        owner_indexes.append(len(repaired))
        repaired.append(dataclasses.replace(entry, name=current_name, title=current_title))

    return repaired


def parse_proxy_fundamentals(
    accession_number: str,
    content: str,
    form_type: str,
    cik: int,
) -> dict[str, list[dict[str, Any]]]:
    """Parse a DEF 14A HTML document into ``sec_executive_record`` rows.

    Parameters
    ----------
    accession_number:
        Accession number of the DEF 14A filing.
    content:
        Raw HTML string of the primary DEF 14A document.
    form_type:
        Form type (DEF 14A, DEF 14A/A, etc.) — stored for audit trail.
    cik:
        CIK of the issuer company.

    Returns
    -------
    dict with key ``"sec_executive_record"`` → list of row dicts.
    Returns ``{"sec_executive_record": []}`` when no SCT is found.
    """
    try:
        from lxml import html as lxml_html
        from edgar.proxy.html_extractor import extract_summary_compensation
    except ImportError:
        return {"sec_executive_record": []}

    # Parse HTML — suppress lxml noise from malformed proxy HTML
    try:
        tree = lxml_html.fromstring(content.encode("utf-8", errors="replace"))
    except Exception:
        return {"sec_executive_record": []}

    try:
        entries = extract_summary_compensation(tree)
    except Exception:
        return {"sec_executive_record": []}

    if not entries:
        return {"sec_executive_record": []}

    # Same defensive contract as every other fallible step above: a change in
    # what edgartools returns degrades to "no records", never an exception out
    # of a parser.
    try:
        entries = _repair_entry_names(list(entries))
    except Exception:
        return {"sec_executive_record": []}

    if not entries:
        return {"sec_executive_record": []}

    rows: list[dict[str, Any]] = []
    for entry in entries:
        raw_title = getattr(entry, "title", None) or ""
        rows.append(
            {
                "cik": int(cik),
                "accession_number": accession_number,
                "fiscal_year": int(entry.year) if entry.year else None,
                "exec_name": str(entry.name).strip() if entry.name else None,
                "exec_role": _infer_role(raw_title) or (raw_title[:200] if raw_title else None),
                "total_comp": _int_to_float(entry.total),
                "base_salary": _int_to_float(entry.salary),
                "bonus": _int_to_float(entry.bonus),
                "stock_awards": _int_to_float(entry.stock_awards),
                "option_awards": _int_to_float(entry.option_awards),
                "non_equity_incentive": _int_to_float(entry.non_equity_incentive),
                "parser_version": PARSER_VERSION,
            }
        )

    return {"sec_executive_record": rows}


def _int_to_float(value: int | None) -> float | None:
    """Convert an Optional[int] compensation value to Optional[float]."""
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
