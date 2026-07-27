"""Unit tests for ERDP-04 transcript MVP Explore product."""

from __future__ import annotations

import unittest
from datetime import date

from edgar_warehouse.explore.transcript_events import (
    PILOT_CIKS,
    TranscriptRowError,
    build_transcript_events_table,
    derive_ir_event_id,
    load_firm_manual_csv,
    normalize_transcript_row,
    register_ir_pointer,
    store_transcript_text,
    transcript_event_key,
)


class NormalizeTests(unittest.TestCase):
    def test_minimal_row(self) -> None:
        row = normalize_transcript_row(
            {
                "cik": "0000320193",
                "event_id": "fy2026q3",
                "event_type": "earnings_call",
                "event_date": "2026-07-31",
                "storage_uri": "https://investor.apple.com/fy2026q3-call",
                "source_system": "ir_website",
            }
        )
        self.assertEqual(row["cik"], 320193)
        self.assertEqual(row["language"], "en")
        self.assertIsNotNone(row["event_key"])

    def test_missing_storage_uri_rejected(self) -> None:
        """A04 integrity rule 1: storage_uri non-null and non-empty."""
        with self.assertRaises(TranscriptRowError):
            normalize_transcript_row(
                {
                    "cik": 1,
                    "event_id": "e1",
                    "event_type": "earnings_call",
                    "event_date": "2026-01-01",
                    "storage_uri": "",
                    "source_system": "firm_manual",
                }
            )

    def test_invalid_event_type_rejected(self) -> None:
        with self.assertRaises(TranscriptRowError):
            normalize_transcript_row(
                {
                    "cik": 1,
                    "event_id": "e1",
                    "event_type": "quarterly_bake_sale",
                    "event_date": "2026-01-01",
                    "storage_uri": "https://example.com/x",
                    "source_system": "firm_manual",
                }
            )

    def test_unknown_source_system_falls_back_to_other(self) -> None:
        row = normalize_transcript_row(
            {
                "cik": 1,
                "event_id": "e1",
                "event_type": "earnings_call",
                "event_date": "2026-01-01",
                "storage_uri": "https://example.com/x",
                "source_system": "some_new_vendor",
            }
        )
        self.assertEqual(row["source_system"], "other")

    def test_s3_without_sha_logs_warning_but_does_not_raise(self) -> None:
        row = normalize_transcript_row(
            {
                "cik": 1,
                "event_id": "e1",
                "event_type": "earnings_call",
                "event_date": "2026-01-01",
                "storage_uri": "s3://bucket/transcripts/cik=1/event_id=e1/transcript.txt",
                "source_system": "firm_manual",
            }
        )
        self.assertIsNone(row["content_sha256"])

    def test_event_key_deterministic_and_excludes_as_of(self) -> None:
        """Natural key is (cik, event_id, source_system) -- no as_of component."""
        k1 = transcript_event_key(1, "e1", "ir_website")
        k2 = transcript_event_key(1, "e1", "ir_website")
        self.assertEqual(k1, k2)

    def test_arrow_table_schema(self) -> None:
        table = build_transcript_events_table(
            [
                {
                    "cik": 320193,
                    "event_id": "fy2026q3",
                    "event_type": "earnings_call",
                    "event_date": date(2026, 7, 31),
                    "storage_uri": "https://investor.apple.com/fy2026q3-call",
                    "source_system": "ir_website",
                }
            ]
        )
        self.assertEqual(table.num_rows, 1)
        names = set(table.schema.names)
        for col in (
            "event_key", "cik", "event_id", "event_type", "event_date",
            "storage_uri", "language", "source_system", "as_of",
        ):
            self.assertIn(col, names)

    def test_empty_rows_returns_empty_table_with_schema(self) -> None:
        table = build_transcript_events_table([])
        self.assertEqual(table.num_rows, 0)
        self.assertIn("event_key", table.schema.names)


class PilotUniverseTests(unittest.TestCase):
    def test_pilot_universe_locked_to_apple(self) -> None:
        """D6: small explicit pilot list, not the full SEC universe."""
        self.assertEqual(PILOT_CIKS, frozenset({320193}))


class IrPointerTests(unittest.TestCase):
    def test_register_ir_pointer_is_pointer_only(self) -> None:
        """A04.6: pointer-only ir_website row for 1 CIK with a live URL."""
        row = register_ir_pointer(
            cik=320193,
            ticker="AAPL",
            event_date=date(2026, 7, 31),
            source_url="https://investor.apple.com/fy2026q3-call",
        )
        self.assertEqual(row["source_system"], "ir_website")
        self.assertEqual(row["storage_uri"], "https://investor.apple.com/fy2026q3-call")
        self.assertIsNone(row["content_sha256"])

    def test_event_id_derivation_is_idempotent(self) -> None:
        """Re-registering the same IR URL yields the same event_id/event_key."""
        e1 = derive_ir_event_id(320193, date(2026, 7, 31), "earnings_call", "https://x.com/a")
        e2 = derive_ir_event_id(320193, date(2026, 7, 31), "earnings_call", "https://x.com/a")
        self.assertEqual(e1, e2)
        row1 = register_ir_pointer(cik=320193, event_date=date(2026, 7, 31), source_url="https://x.com/a")
        row2 = register_ir_pointer(cik=320193, event_date=date(2026, 7, 31), source_url="https://x.com/a")
        self.assertEqual(row1["event_key"], row2["event_key"])


class StoreTextTests(unittest.TestCase):
    def test_store_transcript_text_computes_integrity_fields(self) -> None:
        """A04.5: firm_manual upload + publish for 1 CIK."""

        class FakeStorageRoot:
            def __init__(self) -> None:
                self.writes: dict[str, str] = {}

            def write_text(self, relative_path: str, payload: str) -> str:
                uri = f"s3://fake-bucket/{relative_path}"
                self.writes[uri] = payload
                return uri

        storage_root = FakeStorageRoot()
        text = "Good morning, and welcome to the call."
        row = store_transcript_text(
            cik=320193,
            ticker="AAPL",
            event_date=date(2026, 7, 31),
            text=text,
            storage_root=storage_root,
            source_system="firm_manual",
        )
        self.assertEqual(row["char_count"], len(text))
        self.assertEqual(len(row["content_sha256"]), 64)
        self.assertTrue(row["storage_uri"].startswith("s3://fake-bucket/transcripts/cik=320193/"))
        self.assertEqual(storage_root.writes[row["storage_uri"]], text)


class FirmManualCsvTests(unittest.TestCase):
    def test_load_one_cik_round_trip(self) -> None:
        csv_text = """cik,event_id,event_type,event_date,storage_uri
320193,fy2026q3,earnings_call,2026-07-31,s3://bucket/transcripts/cik=320193/event_id=fy2026q3/transcript.txt
"""
        rows = load_firm_manual_csv(csv_text)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["source_system"], "firm_manual")
        table = build_transcript_events_table(rows)
        self.assertEqual(table.num_rows, 1)


class MultiQuarterHistoryTests(unittest.TestCase):
    """erdp-coverage-promotion ticket 06 §7: is multi-quarter capture for one
    CIK actually blocked by missing ingest code, or already supported?

    `event_id`/`event_key` are derived from `event_date` (`derive_ir_event_id`,
    `transcript_event_key`), so nothing dedupes or collides across quarters --
    this proves that mechanically, not the separate (unresolved) question of
    whether real transcript *content* for those quarters is obtainable.
    """

    class _FakeStorageRoot:
        def __init__(self) -> None:
            self.writes: dict[str, str] = {}

        def write_text(self, relative_path: str, payload: str) -> str:
            uri = f"s3://fake-bucket/{relative_path}"
            self.writes[uri] = payload
            return uri

    def test_two_fiscal_quarters_same_cik_via_ir_pointer_do_not_collide(self) -> None:
        q3 = register_ir_pointer(
            cik=320193,
            event_date=date(2026, 7, 31),
            source_url="https://investor.apple.com/fy2026q3-call",
            fiscal_year=2026,
            fiscal_quarter=3,
        )
        q2 = register_ir_pointer(
            cik=320193,
            event_date=date(2026, 4, 30),
            source_url="https://investor.apple.com/fy2026q2-call",
            fiscal_year=2026,
            fiscal_quarter=2,
        )
        self.assertNotEqual(q3["event_id"], q2["event_id"])
        self.assertNotEqual(q3["event_key"], q2["event_key"])
        table = build_transcript_events_table([q3, q2])
        self.assertEqual(table.num_rows, 2)
        self.assertEqual(set(table.column("cik").to_pylist()), {320193})
        self.assertEqual(
            set(table.column("fiscal_quarter").to_pylist()), {3, 2}
        )

    def test_two_fiscal_quarters_same_cik_via_stored_text_do_not_collide(self) -> None:
        storage_root = self._FakeStorageRoot()
        q3 = store_transcript_text(
            cik=320193,
            event_date=date(2026, 7, 31),
            text="Q3 call text.",
            storage_root=storage_root,
            source_system="firm_manual",
            fiscal_year=2026,
            fiscal_quarter=3,
        )
        q2 = store_transcript_text(
            cik=320193,
            event_date=date(2026, 4, 30),
            text="Q2 call text.",
            storage_root=storage_root,
            source_system="firm_manual",
            fiscal_year=2026,
            fiscal_quarter=2,
        )
        self.assertNotEqual(q3["event_key"], q2["event_key"])
        self.assertNotEqual(q3["storage_uri"], q2["storage_uri"])
        self.assertEqual(len(storage_root.writes), 2)
        table = build_transcript_events_table([q3, q2])
        self.assertEqual(table.num_rows, 2)

    def test_load_firm_manual_records_does_not_dedupe_across_quarters(self) -> None:
        rows = load_firm_manual_csv(
            "cik,event_id,event_type,event_date,storage_uri\n"
            "320193,fy2026q3,earnings_call,2026-07-31,"
            "s3://bucket/transcripts/cik=320193/event_id=fy2026q3/transcript.txt\n"
            "320193,fy2026q2,earnings_call,2026-04-30,"
            "s3://bucket/transcripts/cik=320193/event_id=fy2026q2/transcript.txt\n"
        )
        self.assertEqual(len(rows), 2)
        self.assertEqual({r["event_id"] for r in rows}, {"fy2026q3", "fy2026q2"})


if __name__ == "__main__":
    unittest.main()
