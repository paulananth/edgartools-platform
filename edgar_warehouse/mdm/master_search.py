"""The configured master names (`master_search` in the engine catalog): what a name search reads, prepared by Rust."""
import json


def configuration():
    from .catalog import CATALOG, assert_current
    assert_current()
    return CATALOG.get("master_search")


def prepare(operation, **values):
    import edgar_control
    return json.loads(edgar_control.prepare_text_search(json.dumps(
        {"operation": operation, **values}, ensure_ascii=False, allow_nan=False)))


def name_index(body, spec):
    return prepare("index", fields=spec["name_fields"], body={"fields": {
        field: body.get("fields", {}).get(field, {}) for field in spec["name_fields"]}})


def configured_name(body, spec):
    return prepare("name", fields=spec["name_fields"], body={"fields": {
        field: body.get("fields", {}).get(field, {}) for field in spec["name_fields"]}})
