"""Ticket 17: time one Merge Stage batch of Proving Run size, before and after.

Ticket 05's bundles are gone (a disposable work directory), so this times the
step that was slow with a synthetic batch of the same size: 960 Companies,
each one SEC-like record with a steward bind, in one batch; then a second
batch with a new revision of every record, which re-projects all 960. The
slow function (`company_payload_from_table`) grew with the batch size, so a
same-size batch reproduces it.

Run the same file against two checkouts (main, and ticket 17):

    uv run --extra mdm pytest -q -s -p no:cacheprovider \\
        .scratch/company-mastering/research/17_batch_timing.py
"""

from __future__ import annotations

import json
import time

from tests.integration import test_clean_mdm_postgres as core

postgres = core.postgres
database = core.database
N = 960


def test_time_a_proving_run_sized_batch(database):
    records = [core.source(key=f"c{i:04d}", fields={"name": f"Company {i}"}) for i in range(N)]
    pairs = [core.identity_and_binding(a) for a in records]
    started = time.monotonic()
    core.apply(database, 1, assertions=records, identities=[i for i, _ in pairs],
               decisions=[d for _, d in pairs])
    first = time.monotonic() - started
    revised = [core.source(key=f"c{i:04d}", revision=2, fields={"name": f"Company {i} Inc"})
               for i in range(N)]
    started = time.monotonic()
    core.apply(database, 2, assertions=revised)
    second = time.monotonic() - started
    print("\nTIMING " + json.dumps({"companies": N, "new_batch_seconds": round(first, 1),
                                    "revision_batch_seconds": round(second, 1)}))
