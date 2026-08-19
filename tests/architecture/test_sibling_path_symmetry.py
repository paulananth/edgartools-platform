"""Sibling-path symmetry checks (single-path-per-layer map, Ticket 02).

The shard-publish promotion-race incident (CLAUDE.md's "Shard-publish
promotion-race 5-whys") happened because ``_publish_shard_if_remote``
silently diverged from its sibling ``_publish_silver_database_if_remote`` --
the shard path never got the merge+retry treatment the monolith path got
in PR #222, and nothing (test, lint, or doc) caught the divergence until
three real prod failures forced parity.

This is a narrow, targeted check, not a general single-path-violation
detector (per this repo's Rule 0 precedent from ``/gof-refactor-reviewer``:
cheap and concrete beats general and heavy; the single-path-per-layer map's
Ticket 01 already audited the whole codebase once, by hand). It locks the
one sibling pair that has already diverged in production, so a future edit
to one side without the other fails loudly here instead of silently -- the
same role ``tests/architecture/test_runtime_shim.py`` plays for the
runtime.py/silver.py/gold.py compatibility shims.

Would this have caught the original incident? Yes, in two different ways,
verified against the pre-fix source (``git show eb0a60cb^:...``) rather than
assumed: pre-fix, ``_publish_shard_if_remote_with_retry`` did not exist at
all, so the env-var symmetry test would have failed at the ``import`` line
itself (an ImportError) -- its own comparison logic was never exercised
against a real historical env-var *drift* between two existing wrappers,
only against synthetic snippets (see ``EnvVarExtractionTests`` below). The
merge-symmetry test is the one whose actual assertion logic was exercised
by history: pre-fix, ``merge_candidate_into_canonical`` appeared only in
the monolith function, never in the shard path, so that specific
``assertIn`` would have failed on its own terms, not just at import time.
"""

from __future__ import annotations

import inspect
import re
import unittest


def _env_vars_referenced(source: str) -> set[str]:
    """Every literal env-var name referenced via ``os.environ.get(...)`` or
    ``os.getenv(...)``, single- or double-quoted.

    Matches the literal call shape, not a general env-var read (an alias,
    helper function, or ``os.environ["NAME"]`` subscript would not be
    caught) -- deliberately narrow, matching this file's own scope
    decision to check two specific functions on two specific axes rather
    than build a general detector.
    """
    return set(re.findall(r'os\.(?:environ\.get|getenv)\(\s*[\'"]([A-Z0-9_]+)[\'"]', source))


class EnvVarExtractionTests(unittest.TestCase):
    """Prove the extraction helper is red-capable before trusting it against real code."""

    def test_extracts_multiple_env_vars(self) -> None:
        source = """
        x = os.environ.get("FOO", "1")
        y = os.environ.get("BAR", "2")
        """
        self.assertEqual(_env_vars_referenced(source), {"FOO", "BAR"})

    def test_extracts_getenv_and_single_quoted_calls_too(self) -> None:
        source = """
        x = os.getenv("FOO", "1")
        y = os.environ.get('BAR', '2')
        """
        self.assertEqual(_env_vars_referenced(source), {"FOO", "BAR"})

    def test_detects_asymmetry_between_two_snippets(self) -> None:
        a = 'os.environ.get("SHARED", "1")\nos.environ.get("ONLY_A", "1")'
        b = 'os.environ.get("SHARED", "1")\nos.environ.get("ONLY_B", "1")'
        self.assertNotEqual(_env_vars_referenced(a), _env_vars_referenced(b))


class PublishRetrySiblingSymmetryTests(unittest.TestCase):
    def test_monolith_and_shard_retry_wrappers_reference_the_same_env_vars(self) -> None:
        from edgar_warehouse.application.warehouse_orchestrator import (
            _publish_shard_if_remote_with_retry,
            _publish_silver_database_with_retry,
        )

        monolith_vars = _env_vars_referenced(
            inspect.getsource(_publish_silver_database_with_retry)
        )
        shard_vars = _env_vars_referenced(
            inspect.getsource(_publish_shard_if_remote_with_retry)
        )

        self.assertTrue(monolith_vars, "monolith retry wrapper should reference retry env vars")
        self.assertEqual(
            monolith_vars,
            shard_vars,
            "shard retry wrapper's env vars diverged from the monolith's -- this is "
            "exactly the shape of the shard-publish promotion-race incident "
            "(CLAUDE.md's 5-whys entry). If this is a deliberate change, update both "
            "siblings together, not just one.",
        )

    def test_monolith_and_shard_publish_both_merge_via_merge_candidate_into_canonical(
        self,
    ) -> None:
        from edgar_warehouse.application.warehouse_orchestrator import (
            _publish_shard_if_remote,
            _publish_silver_database_if_remote,
        )

        monolith_source = inspect.getsource(_publish_silver_database_if_remote)
        shard_source = inspect.getsource(_publish_shard_if_remote)

        self.assertIn("merge_candidate_into_canonical", monolith_source)
        self.assertIn(
            "merge_candidate_into_canonical",
            shard_source,
            "shard publish path no longer merges via merge_candidate_into_canonical -- "
            "this is exactly the shape of the shard-publish promotion-race incident "
            "(blind overwrite instead of merge). If this is deliberate, update this "
            "test and CLAUDE.md's 5-whys entry to explain why.",
        )


if __name__ == "__main__":
    unittest.main()
