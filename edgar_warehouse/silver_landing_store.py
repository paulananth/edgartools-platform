"""Store-free silver write path (silver-merge-engine-migration Ticket 14).

Every silver writer records its rows to the Snowflake landing zone through
`_record_landing_passthrough`; the dbt silver models collapse them. The
three tables read back inside a run (`_IN_RUN_LOOKUP_TABLES`, ADR 0011)
are answered from the rows this run recorded. Nothing here opens a
database: `SilverDatabase` (silver_store.py) subclasses this only to keep
its DuckDB engine alive until Ticket 17 deletes it, so the 35 importers and
`open_silver_database` do not churn in the same diff as the engine.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from typing import Any

from edgar_warehouse import silver_schema
from edgar_warehouse.serving.silver_landing_export import LandingExportBuffer

# Sentinel period_start for "instant" (no-duration) XBRL facts -- e.g. balance
# sheet concepts, which the SEC companyfacts API reports with only an "end"
# date and no "start". Keeps period_start NOT NULL so it can sit in the
# sec_financial_fact primary key (added in Stage 2 of the period_end PK fix).
_INSTANT_FACT_PERIOD_START_SENTINEL = "0001-01-01"


# Same-run reads of three landing-only tables (silver-merge-engine-migration
# Ticket 06d, ADR 0011): the writer call that records a row also indexes it,
# and get_filing/get_filing_attachments/get_raw_object answer from that. Per
# table: its key columns, and the columns the old upsert's DO UPDATE SET never
# touched, which keep their first value in the run.
_IN_RUN_LOOKUP_TABLES: dict[str, tuple[tuple[str, ...], frozenset[str]]] = {
    "sec_company_filing": (
        ("accession_number",),
        frozenset({"cik", "act", "file_number", "film_number", "items"}),
    ),
    "sec_filing_attachment": (("accession_number", "document_name"), frozenset()),
    "sec_raw_object": (("raw_object_id",), frozenset({"fetched_at"})),
}


class SilverLandingStore:
    """Records silver rows to the landing export; answers same-run reads."""

    def __init__(self, *, landing_export: LandingExportBuffer | None = None) -> None:
        # Rows of _IN_RUN_LOOKUP_TABLES recorded this run: table -> first key
        # value -> remaining key values -> row.
        self._in_run_rows: dict[str, dict[Any, dict[tuple[Any, ...], dict[str, Any]]]] = {
            table_name: {} for table_name in _IN_RUN_LOOKUP_TABLES
        }
        # When set, every writer below records its rows here for a later
        # flush to the Snowflake landing zone; None makes every write a no-op.
        self.landing_export = landing_export

    def close(self) -> None:
        """Nothing to release; SilverDatabase overrides this to close DuckDB."""

    @contextmanager
    def _shard_advisory_lock(self) -> Iterator[None]:
        """No local file to serialize on; SilverDatabase overrides with a file lock."""
        yield

    def mark_fundamentals_accession_processed(self, mode: str, accession_number: str) -> None:
        """Record that ``mode`` (per-filing | thirteenf) fully wrote this accession.

        Ticket 02 (fundamentals-daily-integration map). Callers must issue
        this only after every real output row for the accession has already
        been written and returned -- this table's whole purpose is letting a
        crash-and-retry never see an accession marked processed without its
        real rows having landed, and this method has no way to enforce that
        ordering itself.

        Landing-only (silver-merge-engine-migration Ticket 12): the readers
        query Snowflake silver, whose dbt model keeps one row per
        (mode, accession_number) by landing `parse_sequence` -- the row from
        the latest load, as the old ON CONFLICT update kept the latest write.
        """
        self._record_landing_passthrough(
            "sec_fundamentals_processed_accession",
            [{"mode": mode, "accession_number": accession_number}],
            defaults={},
            stamp={"processed_at": datetime.now(UTC)},
        )

    def mark_entity_facts_refreshed(self, cik: int) -> None:
        """Record that entity-facts successfully refreshed this CIK just now.

        Ticket 03 (fundamentals-daily-integration map). Callers must issue
        this only after every real output row for the CIK has already been
        written and returned, same ordering contract as
        mark_fundamentals_accession_processed above.

        Landing-only, same as mark_fundamentals_accession_processed above;
        the dbt model keeps one row per cik.
        """
        self._record_landing_passthrough(
            "sec_entity_facts_refresh_watermark",
            [{"cik": int(cik)}],
            defaults={},
            stamp={"entity_facts_refreshed_at": datetime.now(UTC)},
        )

    def replace_company_tickers(
        self,
        rows: list[dict[str, Any]],
        sync_run_id: str,
        *,
        source_name: str = "company_tickers_exchange",
        cause_reference: str | None = None,
    ) -> int:
        """Landing-only (silver-merge-engine-migration Ticket 06e). Callers pass
        bare {cik, ticker, exchange} dicts from the SEC catalogs; each landed
        row adds source_name, source_rank (its position in the whole input,
        skipped rows included), cause_reference when given, and the sync
        stamp. Recording only those bare dicts once landed rows without the
        NOT NULL source_name and suspended LOAD_SILVER_LANDING_TASK
        (silver-snowflake-migration issue 08). A row with no cik or an empty
        ticker is skipped, not raised. The old local DELETE of this
        source_name's earlier snapshot never reached landing: a ticker that
        drops out of a snapshot is a Silver Landing Retirement Record's job."""
        landed_rows: list[dict[str, Any]] = []
        for ordinal, row in enumerate(rows, start=1):
            if row.get("cik") is None or not row.get("ticker"):
                continue
            landed = {
                "cik": row["cik"],
                "ticker": row["ticker"],
                "exchange": row.get("exchange"),
                "source_name": source_name,
                "source_rank": ordinal,
            }
            if cause_reference is not None:
                landed["cause_reference"] = cause_reference
            landed_rows.append(landed)
        return self._record_landing_passthrough(
            "sec_company_ticker", landed_rows, defaults={}, stamp=self._synced_now_stamp(sync_run_id)
        )

    def merge_company(self, rows: list[dict[str, Any]], sync_run_id: str) -> int:
        """Record staged company rows for landing. Returns row count."""
        return self._record_landing_passthrough(
            "sec_company",
            rows,
            defaults={"first_sync_run_id": sync_run_id},
            stamp=self._synced_now_stamp(sync_run_id),
        )

    def merge_addresses(self, rows: list[dict[str, Any]], sync_run_id: str) -> int:
        return self._record_landing_passthrough(
            "sec_company_address", rows, defaults={}, stamp=self._synced_now_stamp(sync_run_id)
        )

    def merge_former_names(self, rows: list[dict[str, Any]], sync_run_id: str) -> int:
        return self._record_landing_passthrough(
            "sec_company_former_name", rows, defaults={}, stamp=self._sync_run_stamp(sync_run_id)
        )

    def merge_submission_files(self, rows: list[dict[str, Any]], sync_run_id: str) -> int:
        return self._record_landing_passthrough(
            "sec_company_submission_file",
            rows,
            defaults={},
            stamp=self._synced_now_stamp(sync_run_id),
        )

    def merge_filings(self, rows: list[dict[str, Any]], sync_run_id: str) -> int:
        # cik is nullable in the DDL, so the NOT NULL check would not catch a
        # missing key that the old values_fn's row["cik"] rejected.
        for row in rows:
            if "cik" not in row:
                raise ValueError(f"sec_company_filing row is missing the 'cik' key: {row!r}")
        return self._record_landing_passthrough(
            "sec_company_filing", rows, defaults={}, stamp=self._synced_now_stamp(sync_run_id)
        )

    def get_filing(self, accession_number: str) -> dict[str, Any] | None:
        rows = self._in_run_lookup("sec_company_filing", accession_number)
        return rows[0] if rows else None

    def stage_submission(
        self,
        *,
        cik: int,
        main_payload: dict[str, Any],
        pagination_payloads: list[tuple[str, dict[str, Any]]],
        sync_run_id: str,
        raw_object_id: str,
        load_mode: str,
        recent_limit: int | None = None,
        filing_min_date: Any = None,
    ) -> dict[str, Any]:
        """Stage one company's full submission: run loaders, record the company
        tables for landing, merge the filing rows locally."""
        with self._shard_advisory_lock():
            return self._stage_submission_locked(
                cik=cik,
                main_payload=main_payload,
                pagination_payloads=pagination_payloads,
                sync_run_id=sync_run_id,
                raw_object_id=raw_object_id,
                load_mode=load_mode,
                recent_limit=recent_limit,
                filing_min_date=filing_min_date,
            )

    def _stage_submission_locked(
        self,
        *,
        cik: int,
        main_payload: dict[str, Any],
        pagination_payloads: list[tuple[str, dict[str, Any]]],
        sync_run_id: str,
        raw_object_id: str,
        load_mode: str,
        recent_limit: int | None = None,
        filing_min_date: Any = None,
    ) -> dict[str, Any]:
        from edgar_warehouse.loaders.bronze_submission_extractors import (
            filter_rows_by_min_filing_date,
            is_reporting_company_entity_type,
            stage_address_loader,
            stage_company_loader,
            stage_former_name_loader,
            stage_manifest_loader,
            stage_pagination_filing_loader,
            stage_recent_filing_loader,
        )

        # individual-filer-company-misclassification map, Ticket 03/04: SEC's
        # own entityType is only knowable once main_payload is fetched (here),
        # so this is the sole place to gate the sec_company/address/former_name
        # writes -- an individual/insider filer (entityType='other') is not a
        # reporting company and must not be written into the company universe.
        is_reporting_company = is_reporting_company_entity_type(main_payload.get("entityType"))
        if is_reporting_company:
            company_rows = stage_company_loader(main_payload, cik, sync_run_id, raw_object_id, load_mode)
            address_rows = stage_address_loader(main_payload, cik, sync_run_id, raw_object_id, load_mode)
            former_name_rows = stage_former_name_loader(main_payload, cik, sync_run_id, raw_object_id, load_mode)
        else:
            company_rows = []
            address_rows = []
            former_name_rows = []
        manifest_rows = stage_manifest_loader(main_payload, cik, sync_run_id, raw_object_id, load_mode)
        recent_rows = filter_rows_by_min_filing_date(
            stage_recent_filing_loader(
                main_payload, cik, sync_run_id, raw_object_id, load_mode, recent_limit=recent_limit
            ),
            filing_min_date,
        )

        rows_written = 0
        company_rows_written = self.merge_company(company_rows, sync_run_id)
        rows_written += company_rows_written
        rows_written += self.merge_addresses(address_rows, sync_run_id)
        rows_written += self.merge_former_names(former_name_rows, sync_run_id)
        rows_written += self.merge_submission_files(manifest_rows, sync_run_id)

        # Collect recent + all pagination-file rows and merge in ONE bulk call
        # instead of one call per pagination file (a well-filed company can
        # have 50+ pagination files). merge_filings' staged-bulk upsert already
        # dedupes correctly when the same accession_number appears more than
        # once across recent/pagination rows, so combining is safe and avoids
        # paying per-call staging-table overhead dozens of times per CIK.
        all_filing_rows = list(recent_rows)
        pagination_accessions: list[str] = []
        for _file_name, pagination_payload in pagination_payloads:
            pagination_rows = filter_rows_by_min_filing_date(
                stage_pagination_filing_loader(
                    pagination_payload, cik, sync_run_id, raw_object_id, load_mode
                ),
                filing_min_date,
            )
            all_filing_rows.extend(pagination_rows)
            pagination_accessions.extend(
                row["accession_number"] for row in pagination_rows if row.get("accession_number")
            )
        rows_written += self.merge_filings(all_filing_rows, sync_run_id)

        return {
            "rows_written": rows_written,
            "company_rows_written": company_rows_written,
            "recent_rows": recent_rows,
            "manifest_rows": manifest_rows,
            "recent_accessions": [
                row["accession_number"] for row in recent_rows if row.get("accession_number")
            ],
            "pagination_accessions": pagination_accessions,
        }

    def merge_current_filing_feed(self, rows: list[dict[str, Any]], sync_run_id: str) -> int:
        # The old loop skipped (never raised on) a falsy accession_number.
        return self._record_landing_passthrough(
            "sec_current_filing_feed",
            [r for r in rows if r.get("accession_number")],
            defaults={},
            stamp=self._synced_now_stamp(sync_run_id),
        )

    def merge_ownership_reporting_owners(self, rows: list[dict[str, Any]], sync_run_id: str) -> int:
        return self._record_landing_passthrough(
            "sec_ownership_reporting_owner", rows, defaults={}, stamp=self._sync_run_stamp(sync_run_id)
        )

    def merge_ownership_non_derivative_txns(self, rows: list[dict[str, Any]], sync_run_id: str) -> int:
        return self._record_landing_passthrough(
            "sec_ownership_non_derivative_txn", rows, defaults={}, stamp=self._sync_run_stamp(sync_run_id)
        )

    def merge_ownership_derivative_txns(self, rows: list[dict[str, Any]], sync_run_id: str) -> int:
        return self._record_landing_passthrough(
            "sec_ownership_derivative_txn", rows, defaults={}, stamp=self._sync_run_stamp(sync_run_id)
        )

    def merge_adv_filings(self, rows: list[dict[str, Any]], sync_run_id: str) -> int:
        return self._record_landing_passthrough(
            "sec_adv_filing", rows, defaults={}, stamp=self._sync_run_stamp(sync_run_id)
        )

    def merge_adv_offices(self, rows: list[dict[str, Any]], sync_run_id: str) -> int:
        return self._record_landing_passthrough(
            "sec_adv_office", rows, defaults={}, stamp=self._sync_run_stamp(sync_run_id)
        )

    def merge_adv_disclosure_events(self, rows: list[dict[str, Any]], sync_run_id: str) -> int:
        return self._record_landing_passthrough(
            "sec_adv_disclosure_event", rows, defaults={}, stamp=self._sync_run_stamp(sync_run_id)
        )

    def merge_adv_private_funds(self, rows: list[dict[str, Any]], sync_run_id: str) -> int:
        return self._record_landing_passthrough(
            "sec_adv_private_fund", rows, defaults={}, stamp=self._sync_run_stamp(sync_run_id)
        )

    def merge_adv_firm_roster(self, rows: list[dict[str, Any]], sync_run_id: str) -> int:
        return self._record_landing_passthrough(
            "sec_adv_firm_roster", rows, defaults={}, stamp=self._sync_run_stamp(sync_run_id)
        )

    def merge_subsidiary_evidence(self, rows: list[dict[str, Any]], sync_run_id: str) -> int:
        return self._record_landing_passthrough(
            "sec_subsidiary_evidence",
            rows,
            defaults={"immediate_parent_known": False, "parser_version": "subsidiary_exhibit_v1"},
            stamp=self._sync_run_stamp(sync_run_id),
        )

    def merge_auditor_report_evidence(self, rows: list[dict[str, Any]], sync_run_id: str) -> int:
        return self._record_landing_passthrough(
            "sec_auditor_report_evidence",
            rows,
            defaults={"parser_version": "auditor_evidence_v1"},
            stamp=self._sync_run_stamp(sync_run_id),
        )

    def merge_pcaob_firm_identities(self, rows: list[dict[str, Any]], sync_run_id: str) -> int:
        return self._record_landing_passthrough(
            "sec_pcaob_firm_identity", rows, defaults={}, stamp=self._sync_run_stamp(sync_run_id)
        )

    def upsert_raw_object(self, row: dict[str, Any]) -> None:
        for required in ("raw_object_id", "source_url", "storage_path", "sha256", "fetched_at", "http_status"):
            if row.get(required) is None:
                raise ValueError(f"upsert_raw_object: required field '{required}' is missing or None")
        self._record_landing_passthrough("sec_raw_object", [row], defaults={}, stamp={})

    def get_raw_object(self, raw_object_id: str) -> dict[str, Any] | None:
        rows = self._in_run_lookup("sec_raw_object", raw_object_id)
        return rows[0] if rows else None

    def merge_filing_attachments(self, rows: list[dict[str, Any]], sync_run_id: str) -> int:
        for row in rows:
            for required in ("accession_number", "document_name", "document_type", "document_url"):
                if not row.get(required):
                    raise ValueError(f"merge_filing_attachments: required field '{required}' is missing or None in row {row}")
        return self._record_landing_passthrough(
            "sec_filing_attachment",
            rows,
            defaults={"is_primary": False},
            stamp=self._sync_run_stamp(sync_run_id),
        )

    def get_filing_attachments(self, accession_number: str) -> list[dict[str, Any]]:
        """Return all attachment rows this run recorded for the given accession number."""
        return self._in_run_lookup("sec_filing_attachment", accession_number)

    def upsert_filing_text(self, row: dict[str, Any]) -> None:
        """Record a filing text extraction row, landing-only
        (silver-merge-engine-migration Ticket 06e); the dbt model collapses
        rows on (accession_number, text_version).

        Raises ValueError if any required field is missing or None, before
        anything is recorded.
        """
        for required in (
            "accession_number",
            "text_version",
            "source_document_name",
            "text_storage_path",
            "text_sha256",
            "char_count",
            "extracted_at",
        ):
            if row.get(required) is None:
                raise ValueError(
                    f"upsert_filing_text: required field '{required}' is missing or None"
                )
        self._record_landing_passthrough("sec_filing_text", [row], defaults={}, stamp={})

    def _record_landing_passthrough(
        self,
        table_name: str,
        rows: list[dict[str, Any]],
        *,
        defaults: dict[str, Any],
        stamp: dict[str, Any],
    ) -> int:
        """Landing-only write for a table whose local DuckDB copy is dead
        (silver-merge-engine-migration Tickets 02-06): DuckDB Retirement
        Cutover Ticket 10 made the local store ephemeral, so the QUALIFY/ON
        CONFLICT merge these tables used to run computed a result no later run
        consumed. The dbt silver models collapse the raw landing rows on the
        old ON CONFLICT keys. Rows of the `_IN_RUN_LOOKUP_TABLES` are also
        indexed for this run's own `get_*` reads (Ticket 06d), with or without
        a landing buffer attached; raw SQL on local DuckDB finds none of them.

        `defaults` mirrors the old values_fn's `r.get(col, default)` fills
        exactly -- applied only when the key is absent, never over an
        explicit None. `stamp` adds write-time columns the landing schema
        carries but the caller doesn't supply (facts/flags: `ingested_at` +
        the Ticket 33 validity trio; per-filing and 13F tables:
        `ingested_at`; company submission, filing, attachment, ownership, ADV
        and relationship-source evidence tables and the current filing feed:
        `last_sync_run_id`, plus `last_synced_at` where the table has it
        (company tickers too, Ticket 06e); the two fundamentals markers:
        `processed_at` / `entity_facts_refreshed_at` (Ticket 12); derived,
        raw objects and filing text: nothing, their landing rows are recorded
        as given). A `values_fn` coercion that replaced a present value --
        `bool(...)`, `or ""` -- is applied by the caller before this call,
        since `defaults` only fills absent keys.

        A row that would have violated this table's NOT NULL DDL raises here
        instead of failing the Snowflake load of its whole Parquet file
        later -- the same fail-loud behaviour the DuckDB INSERT had.
        """
        if not rows:
            return 0
        required = self._required_columns(table_name)
        recorded = []
        for row in rows:
            full = {**defaults, **row, **stamp}
            missing = [c for c in required if full.get(c) is None]
            if missing:
                raise ValueError(
                    f"{table_name} row is missing NOT NULL column(s) {missing}: {row!r}"
                )
            recorded.append(full)
        landing_export = getattr(self, "landing_export", None)
        if landing_export is not None:
            landing_export.record(table_name, recorded)
        if table_name in _IN_RUN_LOOKUP_TABLES:
            self._remember_in_run(table_name, recorded)
        return len(recorded)

    @staticmethod
    def _required_columns(table_name: str) -> tuple[str, ...]:
        """NOT NULL columns from the silver schema snapshot
        (edgar_warehouse/silver_schema.py, silver-merge-engine-migration
        Ticket 13; generated from the live DDL while DuckDB exists). Defaulted
        ones count too -- DuckDB rejected an explicit NULL there as well, and
        `defaults`/`stamp` are what supply them now. Fails closed on a table
        the snapshot does not know: every landing-only table has at least
        cik/accession_number NOT NULL, so a misspelled or unsnapshotted table
        must not pass as "nothing required"."""
        try:
            return silver_schema.REQUIRED[table_name]
        except KeyError:
            raise ValueError(f"{table_name}: not in the silver schema snapshot") from None

    def _remember_in_run(self, table_name: str, rows: list[dict[str, Any]]) -> None:
        """Index recorded rows for this run's own reads. A key that recurs keeps
        the old upsert's rule: first-value columns from its earliest write, every
        other column from its latest. Stores copies, so a landing row is never
        mutated."""
        key_columns, first_value_columns = _IN_RUN_LOOKUP_TABLES[table_name]
        by_first_key = self._in_run_rows[table_name]
        for row in rows:
            group = by_first_key.setdefault(row[key_columns[0]], {})
            rest_key = tuple(row[column] for column in key_columns[1:])
            merged = dict(row)
            earlier = group.get(rest_key)
            if earlier is not None:
                merged.update({column: earlier.get(column) for column in first_value_columns})
            group[rest_key] = merged

    def _in_run_lookup(self, table_name: str, first_key: Any) -> list[dict[str, Any]]:
        """Rows this run recorded under `first_key`, as copies carrying every
        column of the schema snapshot in order (None where the write had
        none): the row shape `SELECT *` returned before the table went
        landing-only."""
        columns = silver_schema.COLUMNS[table_name]
        return [
            {column: row.get(column) for column in columns}
            for row in self._in_run_rows[table_name].get(first_key, {}).values()
        ]

    @staticmethod
    def _ingested_at_stamp() -> dict[str, Any]:
        """ingested_at was DuckDB's DEFAULT NOW() and every ON CONFLICT
        branch's `ingested_at = now()`; landing rows now carry it per write.
        Gold models output it and MDM's EMPLOYED_BY derivation filters
        sec_executive_record/sec_employment_event on it as a watermark."""
        return {"ingested_at": datetime.now(UTC)}

    @staticmethod
    def _sync_run_stamp(sync_run_id: str) -> dict[str, Any]:
        """`last_sync_run_id` for tables that record which sync run last
        wrote a row (company submission, ticker, filing, attachment,
        ownership, ADV and relationship-source evidence tables, the current
        filing feed). The old `values_fn`s always wrote the call's
        `sync_run_id`, whatever the row said, so this overrides a row-supplied
        value."""
        return {"last_sync_run_id": sync_run_id}

    @classmethod
    def _synced_now_stamp(cls, sync_run_id: str) -> dict[str, Any]:
        """`last_sync_run_id` plus `last_synced_at` (now), for tables that
        also record when a sync last wrote the row."""
        return {**cls._sync_run_stamp(sync_run_id), "last_synced_at": datetime.now(UTC)}

    @classmethod
    def _current_row_stamp(cls) -> dict[str, Any]:
        """Write-time columns for sec_financial_fact/sec_accounting_flag
        landing rows: `ingested_at` plus the Ticket 33 validity trio. Any row
        present in a write is current as of that write (is_current=True/
        valid_to=None need no read-back); valid_from is this write's time, a
        deliberate last-write-wins simplification for the landing/dbt
        collapse."""
        stamp = cls._ingested_at_stamp()
        return {**stamp, "valid_from": stamp["ingested_at"], "valid_to": None, "is_current": True}

    def merge_financial_facts(self, rows: list[dict[str, Any]], sync_run_id: str) -> int:
        return self._record_landing_passthrough(
            "sec_financial_fact",
            rows,
            defaults={
                "period_start": _INSTANT_FACT_PERIOD_START_SENTINEL,
                "form_type": "",
                "segment": "consolidated",
            },
            stamp=self._current_row_stamp(),
        )

    def merge_financial_derived(self, rows: list[dict[str, Any]], sync_run_id: str) -> int:
        return self._record_landing_passthrough(
            "sec_financial_derived",
            rows,
            defaults={"form_type": ""},
            stamp={},
        )

    def merge_earnings_releases(self, rows: list[dict[str, Any]], sync_run_id: str) -> int:
        return self._record_landing_passthrough(
            "sec_earnings_release",
            [
                {
                    **r,
                    "has_non_gaap": bool(r.get("has_non_gaap", False)),
                    "has_guidance": bool(r.get("has_guidance", False)),
                }
                for r in rows
            ],
            defaults={},
            stamp=self._ingested_at_stamp(),
        )

    def merge_guidance_facts(self, rows: list[dict[str, Any]], sync_run_id: str) -> int:
        return self._record_landing_passthrough(
            "sec_guidance_fact",
            [
                {
                    **r,
                    "accession_number": r.get("accession_number") or "",
                    "is_non_gaap": bool(r.get("is_non_gaap", False)),
                }
                for r in rows
            ],
            defaults={"confidence": "medium"},
            stamp=self._ingested_at_stamp(),
        )

    def merge_guidance_fact_rejects(self, rows: list[dict[str, Any]], sync_run_id: str) -> int:
        return self._record_landing_passthrough(
            "sec_guidance_fact_reject",
            [{**r, "accession_number": r.get("accession_number") or ""} for r in rows],
            defaults={},
            stamp=self._ingested_at_stamp(),
        )

    def merge_accounting_flags(self, rows: list[dict[str, Any]], sync_run_id: str) -> int:
        return self._record_landing_passthrough(
            "sec_accounting_flag",
            rows,
            defaults={"form_type": "10-K"},
            stamp=self._current_row_stamp(),
        )

    def merge_executive_records(self, rows: list[dict[str, Any]], sync_run_id: str) -> int:
        return self._record_landing_passthrough(
            "sec_executive_record", rows, defaults={}, stamp=self._ingested_at_stamp()
        )

    def merge_employment_events(self, rows: list[dict[str, Any]], sync_run_id: str) -> int:
        return self._record_landing_passthrough(
            "sec_employment_event", rows, defaults={}, stamp=self._ingested_at_stamp()
        )

    def merge_thirteenf_holdings(self, rows: list[dict[str, Any]], sync_run_id: str) -> int:
        return self._record_landing_passthrough(
            "sec_thirteenf_holding", rows, defaults={}, stamp=self._ingested_at_stamp()
        )

    def merge_thirteenf_filings(self, rows: list[dict[str, Any]], sync_run_id: str) -> int:
        return self._record_landing_passthrough(
            "sec_thirteenf_filing",
            [{**r, "confidential_omission": bool(r.get("confidential_omission", False))} for r in rows],
            defaults={"effective_status": "effective", "parser_version": "1"},
            stamp=self._ingested_at_stamp(),
        )
