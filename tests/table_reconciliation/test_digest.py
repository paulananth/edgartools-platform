from __future__ import annotations

import datetime

from edgar_warehouse.table_reconciliation.digest import (
    normalize_row,
    sorted_key_set_digest,
    sorted_semantic_row_digest,
)


def test_sorted_key_set_digest_is_order_independent():
    keys_a = [(1, "x"), (2, "y")]
    keys_b = [(2, "y"), (1, "x")]
    assert sorted_key_set_digest(keys_a) == sorted_key_set_digest(keys_b)


def test_sorted_key_set_digest_detects_a_real_difference():
    keys_a = [(1, "x"), (2, "y")]
    keys_b = [(1, "x"), (2, "z")]
    assert sorted_key_set_digest(keys_a) != sorted_key_set_digest(keys_b)


def test_sorted_key_set_digest_handles_none_values_without_crashing():
    keys = [(1, None), (None, "x")]
    # Just must not raise -- ordering across None/str/int is only used for
    # hashing determinism, not content correctness.
    digest = sorted_key_set_digest(keys)
    assert isinstance(digest, str)


def test_normalize_row_converts_datetimes_to_isoformat():
    row = {"a": datetime.date(2026, 1, 1), "b": 1}
    normalized = normalize_row(row)
    assert normalized["a"] == "2026-01-01"
    assert normalized["b"] == 1


def test_normalize_row_excludes_declared_columns():
    row = {"a": 1, "b": 2, "authority_ts": "2026-01-01"}
    normalized = normalize_row(row, exclude=frozenset({"authority_ts"}))
    assert "authority_ts" not in normalized
    assert normalized == {"a": 1, "b": 2}


def test_sorted_semantic_row_digest_is_order_independent():
    rows_a = [{"k": 1, "v": "x"}, {"k": 2, "v": "y"}]
    rows_b = [{"k": 2, "v": "y"}, {"k": 1, "v": "x"}]
    digest_a = sorted_semantic_row_digest(rows_a, key_columns=("k",), exclude_columns=frozenset())
    digest_b = sorted_semantic_row_digest(rows_b, key_columns=("k",), exclude_columns=frozenset())
    assert digest_a == digest_b


def test_sorted_semantic_row_digest_is_column_order_independent():
    rows_a = [{"k": 1, "v": "x", "w": "y"}]
    rows_b = [{"w": "y", "v": "x", "k": 1}]
    digest_a = sorted_semantic_row_digest(rows_a, key_columns=("k",), exclude_columns=frozenset())
    digest_b = sorted_semantic_row_digest(rows_b, key_columns=("k",), exclude_columns=frozenset())
    assert digest_a == digest_b


def test_sorted_semantic_row_digest_detects_real_content_difference():
    rows_a = [{"k": 1, "v": "x"}]
    rows_b = [{"k": 1, "v": "different"}]
    digest_a = sorted_semantic_row_digest(rows_a, key_columns=("k",), exclude_columns=frozenset())
    digest_b = sorted_semantic_row_digest(rows_b, key_columns=("k",), exclude_columns=frozenset())
    assert digest_a != digest_b


def test_sorted_semantic_row_digest_ignores_excluded_column_differences():
    rows_a = [{"k": 1, "v": "x", "authority_ts": "2026-01-01T00:00:00"}]
    rows_b = [{"k": 1, "v": "x", "authority_ts": "2026-06-01T00:00:00"}]
    digest_a = sorted_semantic_row_digest(
        rows_a, key_columns=("k",), exclude_columns=frozenset({"authority_ts"})
    )
    digest_b = sorted_semantic_row_digest(
        rows_b, key_columns=("k",), exclude_columns=frozenset({"authority_ts"})
    )
    assert digest_a == digest_b
