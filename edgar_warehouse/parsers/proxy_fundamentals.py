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
PARSER_VERSION = "2"

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
# A word that belongs to both must be added to both.
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

# A trailing reference marker on a name cell: "Yoor,(1)", "Smith*", "Smith (2)",
# "Smith†". Stripped from the name only; the extractor already handles markers
# inside dollar cells.
_NAME_MARKER_RE = re.compile(r"[,\s]*(?:\((?:\d+|[a-z])\)|[*†‡§¶]+)\s*$", re.IGNORECASE)

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
_CAMEL_TITLE_RE = re.compile(
    r"(?<=[a-z])(?=(?:"
    + "|".join(
        sorted(
            {form for word in _TITLE_STARTS for form in (word.capitalize(), word.upper())},
            key=len,
            reverse=True,
        )
    )
    + r")\b)"
)


def _strip_name_markers(cell: str) -> str:
    """Remove trailing footnote/reference markers from a name cell."""
    previous = None
    text = cell.strip()
    while text != previous:
        previous = text
        text = _NAME_MARKER_RE.sub("", text).strip()
    return text.rstrip(",").strip()


def _is_title_word(token: str, vocabulary: frozenset[str] | tuple[str, ...]) -> bool:
    """True when a token, or either half of a hyphenated one, is position text."""
    bare = token.lower().strip(".'’-")
    if bare in vocabulary:
        return True
    return any(part and part in vocabulary for part in bare.split("-"))


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
    """
    cell = _CAMEL_TITLE_RE.sub(" ", cell.strip())
    tokens = _NAME_TOKEN_RE.findall(cell)
    if not tokens:
        return None, cell.strip()

    cut = len(tokens)
    for index, token in enumerate(tokens):
        if _is_title_word(token, _TITLE_STARTS):
            cut = index
            break

    if cut < 2:
        return None, cell.strip()

    # A cut can still leave position text in front of it ("Marketing Services",
    # "Director of Wholesale Banking"). A person's name carries no position
    # vocabulary at all.
    if any(_is_title_word(token, _TITLE_WORDS) for token in tokens[:cut]):
        return None, cell.strip()

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
    name = name.strip().rstrip(",").strip()
    if len(_NAME_TOKEN_RE.findall(name)) < 2:
        return None, cell.strip()
    return name, trailing


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
        raw_name = _strip_name_markers(str(getattr(entry, "name", "") or ""))
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
