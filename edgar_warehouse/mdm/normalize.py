"""Thin wrappers around MDMRuleEngine normalization methods.

Kept as a separate module so resolvers can import small functions without
depending on the full engine type.
"""
from __future__ import annotations

from typing import Optional

from edgar_warehouse.mdm.rules import MDMRuleEngine


def normalize_entity_name(engine: MDMRuleEngine, name: Optional[str]) -> Optional[str]:
    return engine.normalize_name(name)


def normalize_officer_title(engine: MDMRuleEngine, title: Optional[str]) -> Optional[str]:
    return engine.normalize_title(title)


def normalize_address(engine: MDMRuleEngine, address: Optional[dict]) -> Optional[dict]:
    return engine.normalize_address(address)
