"""Store one try as a draft under the version label in the pasted rule."""

from __future__ import annotations

import json

from edgar_warehouse.control_contract import Blocked


def store_draft(case) -> dict:
    """Store the pasted rule as a draft. A rule with no version is not stored."""
    label, document = _labeled(case)
    if label is None:
        return document
    from .db import Rules, get_engine

    engine = get_engine()
    try:
        saved = Rules(engine).save(
            kind="try", name=case["family"], version=label, body=document, case=case)
    except Blocked as error:
        if str(error) != "This version is already stored":
            raise
        return {"refused": "This version is already stored."}
    finally:
        engine.dispose()
    return {"stored": saved["version"], "digest": saved["digest"], "status": saved["status"]}


def _labeled(case):
    if not isinstance(case, dict):
        return None, {"refused": "The draft is not stored."}
    family = case.get("family")
    if not isinstance(family, str) or not family or len(family) > 128:
        return None, {"refused": "The draft is not stored."}
    rule = case.get("rule")
    if not isinstance(rule, str):
        return None, {"refused": "The version label is not there."}
    try:
        document = json.loads(rule)
    except json.JSONDecodeError:
        return None, {"refused": "The version label is not there."}
    if not isinstance(document, dict):
        return None, {"refused": "The version label is not there."}
    label = document.get("version")
    if not isinstance(label, str) or not label.strip():
        return None, {"refused": "The version label is not there."}
    if len(label) > 128:
        return None, {"refused": "The version label is too long."}
    return label, document
