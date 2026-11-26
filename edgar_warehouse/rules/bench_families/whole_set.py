"""Try: summarize every row with one reduce plan.

The rule box holds a document with a `reduce` block as JSON. The input is the
rows, as JSON: a group name from the plan and that group's rows. The answer is
what `ReductionEngine.finish` returns for those rows: for each group, one row
per key, in key order.
"""

import json

from edgar_warehouse.rules.source_engine import ReductionEngine

title = "Summarize every row"
inputs = [
    {"name": "rows", "label": "The rows, as JSON: a group name from the plan and its rows (leave empty for none)"},
]


def run(inputs, rule):
    try:
        document = json.loads(rule)
    except (TypeError, ValueError):
        return {"refused": "The rule is not JSON."}
    if not isinstance(document, dict):
        return {"refused": "The rule is not one JSON object."}
    plan = document.get("reduce")
    if not isinstance(plan, dict):
        return {"refused": "The rule has no reduce block."}
    rows = _rows(inputs.get("rows"))
    if "refused" in rows:
        return rows
    try:
        engine = ReductionEngine(plan)
        for group, batch in rows["groups"].items():
            engine.push(group, batch)
        summaries = engine.finish()
    except (TypeError, ValueError) as error:
        return {"refused": str(error)}
    return {"groups": summaries}


def _rows(text):
    if text is None:
        return {"refused": "The rows are not there."}
    if not isinstance(text, str):
        return {"refused": "The rows are not text."}
    if not text.strip():
        return {"groups": {}}
    try:
        groups = json.loads(text)
    except ValueError:
        return {"refused": "The rows are not JSON."}
    if not isinstance(groups, dict) or not all(isinstance(batch, list) for batch in groups.values()):
        return {"refused": "The rows are not a JSON object of group names and lists of rows."}
    return {"groups": groups}
