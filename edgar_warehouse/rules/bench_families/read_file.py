"""Try: read a file with one read document.

The rule box holds the read document as JSON. The inputs are the file's text and
the lookup lists (a JSON object of list name to a list of texts). The answer is
what `SourceEngine.read` returns: the tables and the records set aside.
"""

import json

from edgar_warehouse.rules.source_engine import SourceEngine, SourceRejected

title = "Read the file"
inputs = [
    {"name": "file", "label": "The file, as text"},
    {"name": "lookups", "label": "Lookup lists, as JSON: a list name and its texts (leave empty for none)"},
]


def run(inputs, rule):
    try:
        document = json.loads(rule)
    except (TypeError, ValueError):
        return {"refused": "The read document is not JSON."}
    if not isinstance(document, dict):
        return {"refused": "The read document is not one JSON object."}
    lookups = _lookups(inputs.get("lookups"))
    if "refused" in lookups:
        return lookups
    file = inputs.get("file")
    if not isinstance(file, str):
        return {"refused": "The file is not there."}
    try:
        reading = SourceEngine(document).read(file.encode("utf-8"), lookups=lookups["lists"])
    except SourceRejected as error:
        return {"refused": str(error)}
    except (TypeError, ValueError) as error:
        return {"refused": str(error)}
    return {"tables": reading.tables, "deferred": reading.deferred}


def _lookups(text):
    if text is None or (isinstance(text, str) and not text.strip()):
        return {"lists": {}}
    try:
        lists = json.loads(text)
    except (TypeError, ValueError):
        return {"refused": "The lookup lists are not JSON."}
    if not isinstance(lists, dict) or not all(
        isinstance(values, list) and all(isinstance(value, str) for value in values)
        for values in lists.values()
    ):
        return {"refused": "The lookup lists are not a JSON object of lists of texts."}
    return {"lists": lists}
