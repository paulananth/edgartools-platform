"""Regression: warehouse image must import item_502 without missing transitive CLI deps.

spaCy 3.8 does `from click import NoSuchOption` via spacy.cli on plain
`import spacy`. Newer typer no longer depends on the click package, so
warehouse images that only install --extra s3 must list click explicitly.
"""

from __future__ import annotations


def test_item_502_import_requires_click_and_spacy() -> None:
    import click  # noqa: F401
    import spacy  # noqa: F401

    from edgar_warehouse.parsers.item_502 import PARSER_NAME, PARSER_VERSION, parse_item_502

    assert PARSER_NAME == "item_502"
    assert PARSER_VERSION == "5"
    assert callable(parse_item_502)
