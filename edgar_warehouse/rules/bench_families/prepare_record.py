"""Try: prepare the MDM record from a contract with a fixed entity type.

The rule box holds the contract as JSON: `schema_version` and an `adapter` that
states the entity type (`kind`), the record key, the identifiers and the reading
of the row. The inputs are the row, the source code and the publication. The
answer is what `edgar_warehouse.mdm.adapters.normalize` returns: the prepared
record. A contract that contains `classification` takes its entity type from a
rule, so it is refused here before `normalize` runs.
"""

import json

from edgar_warehouse.mdm.adapters import MappingError, UnsupportedRecord, normalize
from edgar_warehouse.mdm.store import Conflict
from edgar_warehouse.rules.source_engine import SourceRejected

title = "Prepare the MDM record"
inputs = [
    {"name": "row", "label": "The row, as JSON"},
    {"name": "source", "label": "The source code, for example example.records.v1"},
    {"name": "publication",
     "label": "The publication, as JSON: publication_key, revision, artifact_sha256 and member"},
]

PUBLICATION_KEYS = ("publication_key", "revision", "artifact_sha256", "member")
OTHER_PAGE = "Prepare a record whose entity type comes from a rule"


def run(inputs, rule):
    try:
        contract = json.loads(rule)
    except (TypeError, ValueError):
        return {"refused": "The contract is not JSON."}
    if not isinstance(contract, dict):
        return {"refused": "The contract is not one JSON object."}
    adapter = contract.get("adapter")
    if not isinstance(adapter, dict):
        return {"refused": "The contract has no adapter block."}
    if "classification" in contract or "classification" in adapter:
        return {"refused": f"This contract contains classification, which names an entity type rule. "
                           f"Try it on the page '{OTHER_PAGE}'."}
    row = _json(inputs.get("row"), "row")
    if "refused" in row:
        return row
    publication = _json(inputs.get("publication"), "publication")
    if "refused" in publication:
        return publication
    source = inputs.get("source")
    if not isinstance(source, str) or not source.strip():
        return {"refused": "The source code is not there."}
    if not isinstance(publication["value"], dict):
        return {"refused": "The publication is not one JSON object."}
    missing = [name for name in PUBLICATION_KEYS if name not in publication["value"]]
    if missing:
        return {"refused": f"The publication has no {', '.join(missing)}."}
    try:
        record = normalize(row["value"], source_code=source.strip(), contract=contract,
                           publication=publication["value"])
    except UnsupportedRecord as error:
        return {"refused": f"The record is set aside: {error.reason}"}
    except (Conflict, MappingError, SourceRejected, KeyError, TypeError, ValueError) as error:
        return {"refused": _said(error)}
    return record


def _json(text, name):
    if not isinstance(text, str) or not text.strip():
        return {"refused": f"The {name} is not there."}
    try:
        return {"value": json.loads(text)}
    except ValueError:
        return {"refused": f"The {name} is not JSON."}


def _said(error):
    if isinstance(error, KeyError):
        return f"The contract or the publication has no {error.args[0]}."
    return str(error)
