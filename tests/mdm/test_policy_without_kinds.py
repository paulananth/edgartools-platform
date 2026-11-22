"""An accepted policy without per-kind rules is usable by mastering."""

from __future__ import annotations

import json
from pathlib import Path

from edgar_warehouse.mastering import reads
from edgar_warehouse.mastering.merge import (
    NAME_ID, Settings, _exact_rules, _waiting_sources, exact_namespaces,
)
from edgar_warehouse.mdm.activation import check_policy


def test_mastering_policy_readers_treat_missing_kinds_as_empty() -> None:
    policy_path = Path(__file__).resolve().parents[1] / "fixtures" / "clean_mdm" / "v1" / "policy.json"
    policy = json.loads(policy_path.read_text(encoding="utf-8"))
    assert "kinds" not in policy
    check_policy(policy)  # the registered fixture policy is accepted without a per-kind map

    settings = Settings(policy=policy, policy_digest="synthetic-fixture", kind="company",
                        as_of="2026-11-22T00:00:00+00:00")
    assert exact_namespaces(settings) == [NAME_ID]
    assert _waiting_sources(settings) == set()
    assert _exact_rules(settings) == []

    class EmptyStore:
        def identifier_holders(self, _namespace: str, _values: list[str]) -> list[str]:
            return []

        def lookup_progress(self, _pin: str) -> tuple[int, str]:
            return 0, ""

        def last_file(self) -> int:
            return 0

        def holding_all(self, _tokens: list[str]) -> list[str]:
            return []

        def master_bodies(self, _entities: list[str]) -> dict:
            return {}

    assert reads.carriers(EmptyStore(), policy, "company", "unknown", "synthetic") == {}
