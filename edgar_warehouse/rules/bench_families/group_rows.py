"""Try: group rows and attach the groups with one combination plan.

The rule box holds the combination contract as JSON: `execution` with the profile
`source.combine`, and `combine` with its groups and output tables. The input is
the readings' tables as JSON: a reading name, a table name, and that table's
rows. The answer is what `combine_tables` returns: the output tables. The
contract is checked by the combine worker's own check before the rows are
combined, and its row limit is applied to the rows pasted.
"""

import json

from edgar_warehouse.control_contract import canonical
from edgar_warehouse.rules.source_engine import combine_tables
from edgar_warehouse.workers import source_combine

title = "Group and attach rows"
inputs = [
    {"name": "tables", "label": "The input tables, as JSON: a reading name, a table name, and its rows"},
]


def run(inputs, rule):
    try:
        contract = _json(rule, "The plan")
        readings = _readings(inputs.get("tables"))
        plan = source_combine._contract(contract, readings)
        rows = sum(len(table) for tables in readings.values() for table in _tables(tables))
        if rows > plan["max_rows"]:
            return {"refused": f"The tables hold {rows} rows; the plan allows {plan['max_rows']}."}
        tables = combine_tables(plan, readings, canonical)
    except (TypeError, ValueError) as error:
        return {"refused": str(error)}
    return {"tables": tables}


def _json(text, what):
    if not isinstance(text, str):
        raise ValueError(f"{what} is not there.")
    try:
        value = json.loads(text, parse_constant=_no_constant)
    except ValueError:
        raise ValueError(f"{what} is not JSON.") from None
    if not isinstance(value, dict):
        raise ValueError(f"{what} is not one JSON object.")
    return value


def _no_constant(name):
    raise ValueError(f"{name} is not a JSON value.")


def _readings(text):
    """The pasted tables, each reading wrapped as the engine takes it."""
    pasted = _json(text, "The input tables")
    for name, tables in pasted.items():
        if not isinstance(tables, dict) or not all(
            isinstance(rows, list) and all(isinstance(row, dict) for row in rows)
            for rows in tables.values()
        ):
            raise ValueError(f"The reading {name} is not a JSON object of tables, each a list of rows.")
    return {name: {"artifacts": [{"tables": tables}]} for name, tables in pasted.items()}


def _tables(reading):
    return reading["artifacts"][0]["tables"].values()
