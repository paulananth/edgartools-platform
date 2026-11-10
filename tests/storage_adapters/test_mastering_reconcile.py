"""Reconciling a source's records: what was delivered, and where each one stands (invented records).

Operator, 2026-11-09: the per-source accounting is part of source onboarding and its skill. The report closes when the
records delivered and not already held equal the records stored, and no waiting record lacks its review.
"""

from edgar_warehouse.mastering.reconcile import reconcile
from tests.storage_adapters.test_mastering import COMPANY, GLEIF, SEC, opened, record, merge


def by_source(db) -> dict:
    db.commit()
    return {row["source"]: row for row in reconcile(db)}


def aside(source: str, key: str) -> dict:
    return {"deferred_id": f"aside-{key}", "source_code": source, "reason": "invented_reason", "body": {}}


def delivered(db):
    companies = [record(SEC, "1", cik="0000000501"), record(SEC, "2", cik="0000000502")]
    waiting = record(GLEIF, "g1", "company", {"name": "INVENTED GLEIF"}, lei="9999000000EXAMPLE016")
    merge.merge_file(db, COMPANY, [*companies, waiting], deferred=[aside(SEC, "x"), aside(SEC, "y")])
    return companies, waiting


def test_every_delivered_record_is_a_golden_record_a_reviewed_wait_or_a_set_aside(database_factory):
    with opened(database_factory) as db:
        delivered(db)
        found = by_source(db)
        expected = {"delivered": 2, "already_held": 0, "new": 2, "stored": 2, "golden_record": 2, "waiting_with_review": 0,
                    "waiting_without_review": 0, "set_aside_delivered": 2, "set_aside_stored": 2,
                    "delivery_not_recorded": False, "closes": True}
        assert {key: found[SEC][key] for key in expected} == expected
        assert (found[GLEIF]["stored"], found[GLEIF]["golden_record"], found[GLEIF]["waiting_with_review"]) == (1, 0, 1)
        assert found[GLEIF]["closes"] and found[GLEIF]["waiting_without_review"] == 0


def test_a_record_delivered_again_counts_as_already_held_and_the_report_still_closes(database_factory):
    with opened(database_factory) as db:
        companies, _ = delivered(db)
        merge.merge_file(db, COMPANY, [companies[0], record(SEC, "3", cik="0000000503")])
        row = by_source(db)[SEC]
        assert (row["delivered"], row["already_held"], row["new"], row["stored"]) == (4, 1, 3, 3) and row["closes"]
        merge.merge_file(db, COMPANY, [companies[0], record(SEC, "3", cik="0000000503")])  # the same file: nothing again
        assert by_source(db)[SEC]["delivered"] == 4


def test_a_stored_record_nobody_delivered_or_a_delivered_record_not_stored_does_not_close(database_factory):
    with opened(database_factory) as db:
        companies, _ = delivered(db)
        db.cursor.execute("delete from mastering_record where assertion_id=%s", [companies[0]["assertion_id"]])
        row = by_source(db)[SEC]
        assert (row["new"], row["stored"], row["closes"]) == (2, 1, False)  # delivered, never stored: not closed


def test_a_waiting_record_with_no_review_does_not_close(database_factory):
    with opened(database_factory) as db:
        _, waiting = delivered(db)
        db.cursor.execute("delete from mastering_review where subject=%s", [waiting["subject"]])
        row = by_source(db)[GLEIF]
        assert (row["waiting_with_review"], row["waiting_without_review"], row["closes"]) == (0, 1, False)


def test_records_merged_before_deliveries_were_recorded_are_never_called_closed(database_factory):
    with opened(database_factory) as db:
        delivered(db)
        db.cursor.execute("delete from mastering_delivery")
        row = by_source(db)[SEC]
        assert row["delivery_not_recorded"] and not row["closes"] and row["stored"] == 2
