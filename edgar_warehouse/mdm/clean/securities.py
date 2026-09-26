"""Publish one Security per 13F CUSIP. Does not create a Company."""

from __future__ import annotations

import re

_CLASS = re.compile(r"\b(?:CL|CLASS)\s*([ABC])\b", re.IGNORECASE)
_OPTION = re.compile(r"\bOPTIONS?\b", re.IGNORECASE)


def publish(holdings: list[dict]) -> dict:
    grouped: dict[str, list[dict]] = {}
    filed = []
    for holding in holdings:
        cusip = str(holding["cusip"]).upper()
        grouped.setdefault(cusip, []).append(holding)
        filed.append(
            {
                "cusip": cusip,
                "filed_title": holding.get("title"),
                "filed_issuer_name": holding.get("issuer_name"),
            }
        )
    securities = [
        {"cusip": cusip, "title": _title(rows)}
        for cusip, rows in grouped.items()
    ]
    return {"securities": securities, "holdings": filed}


def _title(rows: list[dict]) -> str | None:
    classes: set[str] = set()
    option = False
    for row in rows:
        text = str(row.get("title") or "")
        found = {match.group(1).upper() for match in _CLASS.finditer(text)}
        if found:
            classes.update(found)
        elif _OPTION.search(text):
            option = True
    if len(classes) == 1:
        return f"Class {next(iter(classes))}"
    if classes:
        return None
    if option:
        return "Option"
    return None
