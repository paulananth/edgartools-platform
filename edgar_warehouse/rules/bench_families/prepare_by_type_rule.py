"""Try: prepare the MDM record whose entity type comes from a rule.

The rule box holds the contract as JSON: `schema_version` and an `adapter` that
names a `classification` (the entity type's block in the policy, the rule id and
the rule version) and states no `kind`. The inputs are the row, the source code,
the publication and the policy, as JSON: the `kinds` blocks that hold the rule
and the `automatic_rules` that switch a verdict on. The answer is what
`edgar_warehouse.mdm.adapters.normalize` returns: the prepared record, whose
entity type is the one the rule decided and whose provenance names the rule,
its version and the step.
"""

import json

from edgar_warehouse.mdm.adapters import MappingError, UnsupportedRecord, normalize
from edgar_warehouse.mdm.store import Conflict
from edgar_warehouse.rules.source_engine import SourceRejected

title = "Prepare a record whose entity type comes from a rule"
inputs = [
    {"name": "row", "label": "The row, as JSON"},
    {"name": "source", "label": "The source code, for example example.records.v1"},
    {"name": "publication",
     "label": "The publication, as JSON: publication_key, revision, artifact_sha256 and member"},
    {"name": "policy",
     "label": "The policy, as JSON: kinds, with the entity type rule, and automatic_rules"},
]

PUBLICATION_KEYS = ("publication_key", "revision", "artifact_sha256", "member")
CLASSIFICATION_KEYS = ("kind", "rule_id", "version")
FIXED_PAGE = "Prepare the MDM record"


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
    named = adapter.get("classification")
    if not named:
        return {"refused": f"This contract has no classification in its adapter, so no entity type rule "
                           f"decides the entity type. Try a contract with a fixed entity type on the page "
                           f"'{FIXED_PAGE}'."}
    if "kind" in adapter or "kind_field" in adapter:
        return {"refused": "A contract states an entity type (kind) or names a classification rule, not both."}
    if not isinstance(named, dict):
        return {"refused": "The classification is not one JSON object."}
    missing = [name for name in CLASSIFICATION_KEYS if name not in named]
    if missing:
        return {"refused": f"The classification has no {', '.join(missing)}."}
    row = _json(inputs.get("row"), "row")
    if "refused" in row:
        return row
    publication = _json(inputs.get("publication"), "publication")
    if "refused" in publication:
        return publication
    policy = _json(inputs.get("policy"), "policy")
    if "refused" in policy:
        return policy
    source = inputs.get("source")
    if not isinstance(source, str) or not source.strip():
        return {"refused": "The source code is not there."}
    if not isinstance(publication["value"], dict):
        return {"refused": "The publication is not one JSON object."}
    missing = [name for name in PUBLICATION_KEYS if name not in publication["value"]]
    if missing:
        return {"refused": f"The publication has no {', '.join(missing)}."}
    if not isinstance(policy["value"], dict) or not isinstance(policy["value"].get("kinds"), dict):
        return {"refused": "The policy is not one JSON object with a kinds block."}
    try:
        record = normalize(row["value"], source_code=source.strip(), contract=contract,
                           publication=publication["value"], policy=policy["value"])
    except UnsupportedRecord as error:
        return {"refused": _set_aside(error)}
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


def _set_aside(error):
    said = f"The record is set aside: {error.reason}"
    held = error.detail.get("classification")
    if isinstance(held, dict):
        said += f" (rule {held['rule_id']}, version {held['version']}, step {held['step']}, verdict {held['verdict']})"
    return said


def _said(error):
    if isinstance(error, KeyError):
        return f"The contract, the policy or the publication has no {error.args[0]}."
    return str(error)
