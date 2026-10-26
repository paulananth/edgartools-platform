"""Which identifier values a record gives its master (ticket 138 part A2b).

The operator, 2026-10-25: "bind by CUSIP if matches if not then try isin";
"cusip is a seperate than isin it can never be merges". A filed CUSIP and
ISIN on two Securities bind by the CUSIP; the bind lists the ISIN the other
Security holds as `withheld`, and it is never this Security's. Every reader
that answers which master holds a value, or which values a master holds,
asks here after its own query: the queries differ (by value, by master), the
rule does not. A withheld value stays withheld until a steward revokes the
bind; a revoked bind withholds nothing.
"""

from __future__ import annotations

from collections import defaultdict

from .evidence import instant
from .store import identifier_values, rows

Withheld = dict[str, set[tuple[str, str]]]


def withheld_by(decisions, as_of: str | None = None) -> Withheld:
    """The values each record's live bind withholds, among `decisions` (by
    id, once each) made by `as_of`."""
    by_id = {d["decision_id"]: d for d in decisions
             if as_of is None or instant(d["at"]) <= instant(as_of)}
    revoked = {d["target"] for d in by_id.values() if d["operation"] == "revoke"}
    found: Withheld = defaultdict(set)
    for d in by_id.values():
        if d["operation"] == "bind" and d["decision_id"] not in revoked:
            for w in d.get("withheld") or ():
                found[d["subject"]].add((w["namespace"], w["raw"]))
    return dict(found)


def withheld(conn, subjects, decisions=(), as_of: str | None = None) -> Withheld:
    """`withheld_by` over the stored binds and revocations of `subjects` and
    this batch's `decisions`: one indexed read per subject on either store."""
    from .record_reads import RecordReader

    subjects = sorted(set(subjects))
    stored = []
    if subjects and isinstance(conn, RecordReader):
        stored = [d for d in conn.related_decisions(subjects)
                  if d["operation"] in ("bind", "revoke") and d.get("subject") in subjects]
    elif subjects:
        stored = [r["body"] for r in rows(
            conn,
            """SELECT d.body FROM unnest(CAST(:subjects AS text[])) k(key) CROSS JOIN LATERAL (
                SELECT body FROM mdm.decision WHERE body->>'subject' = k.key
                  AND operation IN ('bind', 'revoke') OFFSET 0) d""",
            subjects=subjects,
        )]
    return withheld_by([*stored, *decisions], as_of)


def given(kept_back: Withheld, subject: str | None, namespace: str, raw) -> list[str]:
    """The values of `raw` (one value or a list) a record gives its master:
    all but those its bind withholds."""
    return [v for v in identifier_values(raw) if (namespace, v) not in kept_back.get(subject, ())]
