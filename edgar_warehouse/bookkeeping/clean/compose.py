"""Fill a composed input: the slots of a unit's `compose` body, each a receipt, into its document.

One pure function, so the engine (receipts read from the database) and a local runner (receipts held in
memory) share it. `receipt_of(dependency)` returns the receipt a dependency names; `place(document)` stores
or addresses a finished document and returns its reference. A slot may itself compose a document, which is
placed first and filled in as its reference."""
from __future__ import annotations


def compose_document(body: dict, receipt_of, place) -> dict:
    filled = {}
    for name, value in body["slots"].items():
        if isinstance(value, list):
            filled[name] = [receipt_of(dependency) for dependency in value]
        elif set(value) == {"compose"}:
            filled[name] = compose_document(value["compose"], receipt_of, place)
        else:
            filled[name] = receipt_of(value)

    def fill(node):
        if isinstance(node, dict):
            return filled[node["slot"]] if set(node) == {"slot"} else {k: fill(v) for k, v in node.items()}
        return [fill(value) for value in node] if isinstance(node, list) else node

    return place(fill(body["document"]))
