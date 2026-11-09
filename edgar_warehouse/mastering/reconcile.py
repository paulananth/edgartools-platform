"""Reconcile each source's records: what was delivered to mastering, and where every one of them stands.

For one source: the records delivered (`mastering_delivery`), those the store already held, the records stored, and of
those the ones with a golden record and the ones waiting, with or without an open review; and the records set aside. It
closes when the delivered records not already held equal the stored ones and no waiting record lacks its review. A source
whose records were merged before deliveries were recorded shows them as `delivery_not_recorded`, never as closed.
"""

from __future__ import annotations


def has_deliveries(store) -> bool:
    """False for a store built before deliveries were recorded: its table does not exist yet."""
    try:
        store.rows("select 1 from mastering_delivery where 1=0")
        return True
    except Exception:
        store.rollback()
        return False


def reconcile(store, source: str | None = None) -> list[dict]:
    pick, args = ("where source_code=%s", [source]) if source else ("", [])
    delivered = {row[0]: row[1:] for row in store.rows(
        f"select source_code, sum(records), sum(repeated), sum(deferred) from mastering_delivery {pick} group by source_code", args)} \
        if has_deliveries(store) else {}
    stored = {row[0]: row[1:] for row in store.rows(
        "select r.source_code, count(*), count(r.entity_id), "
        "sum(case when r.entity_id is null and exists (select 1 from mastering_review v where v.subject=r.subject and v.open_review=1) "
        "then 1 else 0 end) from mastering_record r " + pick.replace("source_code", "r.source_code") + " group by r.source_code", args)}
    set_aside = {row[0]: row[1] for row in store.rows(
        f"select source_code, count(*) from mastering_deferred {pick} group by source_code", args)}
    report = []
    for code in sorted({*delivered, *stored, *set_aside}):
        records, repeated, aside = (int(n or 0) for n in delivered.get(code, (0, 0, 0)))
        held, joined, reviewed = (int(n or 0) for n in stored.get(code, (0, 0, 0)))
        waiting = held - joined
        recorded = records > 0 or held == 0
        report.append({
            "source": code, "delivered": records, "already_held": repeated, "new": records - repeated, "stored": held,
            "golden_record": joined, "waiting_with_review": reviewed, "waiting_without_review": waiting - reviewed,
            "set_aside_delivered": aside, "set_aside_stored": int(set_aside.get(code, 0)),
            "delivery_not_recorded": not recorded,
            "closes": recorded and records - repeated == held and waiting == reviewed,
        })
    return report
