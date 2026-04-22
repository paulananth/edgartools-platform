from __future__ import annotations

import unittest
from datetime import date
from importlib import resources

from edgar_warehouse.application.errors import WarehouseRuntimeError
from edgar_warehouse.infrastructure.dataset_path_catalog import (
    CaptureSpecFactory,
    PathTemplateCatalog,
    WarehousePathResolver,
    load_path_template_catalog,
)


def _default_properties_text() -> str:
    return (
        resources.files("edgar_warehouse.config")
        .joinpath("warehouse_paths.properties")
        .read_text(encoding="utf-8")
    )


class PathTemplateCatalogTests(unittest.TestCase):
    def test_load_default_catalog_from_packaged_resource(self) -> None:
        content = _default_properties_text()
        catalog = load_path_template_catalog()

        self.assertIn("reference.company_tickers.path", content)
        self.assertEqual(
            catalog.get("reference.company_tickers.path"),
            "reference/sec/company_tickers/{date_path}/company_tickers.json",
        )

    def test_catalog_rejects_missing_required_keys(self) -> None:
        content = _default_properties_text().replace(
            "reference.company_tickers.path = reference/sec/company_tickers/{date_path}/company_tickers.json\n",
            "",
        )

        with self.assertRaises(WarehouseRuntimeError):
            PathTemplateCatalog.from_text(content)

    def test_catalog_rejects_unknown_placeholders(self) -> None:
        content = _default_properties_text().replace(
            "reference.company_tickers.path = reference/sec/company_tickers/{date_path}/company_tickers.json",
            "reference.company_tickers.path = reference/sec/company_tickers/{unknown_token}/company_tickers.json",
        )

        with self.assertRaises(WarehouseRuntimeError):
            PathTemplateCatalog.from_text(content)

    def test_catalog_rejects_duplicate_keys(self) -> None:
        content = _default_properties_text() + (
            "\nreference.company_tickers.path = reference/sec/company_tickers/{date_path}/company_tickers.json\n"
        )

        with self.assertRaises(WarehouseRuntimeError):
            PathTemplateCatalog.from_text(content)

    def test_catalog_rejects_invalid_template_definition(self) -> None:
        content = _default_properties_text().replace(
            "text.path = text/sec/cik={cik}/accession={accession_number}/{document_name}",
            "text.path = text/sec/cik={cik}/accession={accession_number}/{document_name",
        )

        with self.assertRaises(WarehouseRuntimeError):
            PathTemplateCatalog.from_text(content)


class WarehousePathResolverTests(unittest.TestCase):
    def setUp(self) -> None:
        self.resolver = WarehousePathResolver(load_path_template_catalog())

    def test_resolver_builds_reference_and_seed_paths(self) -> None:
        fetch_date = date(2026, 4, 22)
        self.assertEqual(
            self.resolver.reference_snapshot_path("company_tickers", fetch_date),
            "reference/sec/company_tickers/2026/04/22/company_tickers.json",
        )
        self.assertEqual(
            self.resolver.reference_snapshot_path("company_tickers_exchange", fetch_date),
            "reference/sec/company_tickers_exchange/2026/04/22/company_tickers_exchange.json",
        )
        self.assertEqual(
            self.resolver.cik_universe_batches_path("run-123"),
            "reference/cik_universe/runs/run-123/cik_batches.jsonl",
        )

    def test_resolver_builds_submission_paths_and_filename_contracts(self) -> None:
        fetch_date = date(2026, 4, 22)
        self.assertEqual(self.resolver.submissions_main_filename(1750), "CIK0000001750.json")
        self.assertEqual(
            self.resolver.submissions_main_path(1750, fetch_date),
            "submissions/sec/cik=1750/main/2026/04/22/CIK0000001750.json",
        )
        self.assertEqual(
            self.resolver.submissions_pagination_path(
                1750,
                fetch_date,
                "CIK0000001750-submissions-001.json",
            ),
            "submissions/sec/cik=1750/pagination/2026/04/22/CIK0000001750-submissions-001.json",
        )

    def test_resolver_builds_daily_index_filing_text_and_export_paths(self) -> None:
        target_date = date(2026, 4, 22)
        self.assertEqual(self.resolver.daily_index_filename(target_date), "form.20260422.idx")
        self.assertEqual(
            self.resolver.daily_index_path(target_date),
            "daily_index/sec/2026/04/22/form.20260422.idx",
        )
        self.assertEqual(
            self.resolver.filing_index_filename("0000001750-26-000001"),
            "000000175026000001-index.html",
        )
        self.assertEqual(
            self.resolver.filing_index_path(1750, "0000001750-26-000001"),
            "filings/sec/cik=1750/accession=0000001750-26-000001/index/000000175026000001-index.html",
        )
        self.assertEqual(
            self.resolver.filing_document_path(
                cik=1750,
                accession_number="0000001750-26-000001",
                section="attachments",
                document_name="nested/path/ex99.htm",
            ),
            "filings/sec/cik=1750/accession=0000001750-26-000001/attachments/ex99.htm",
        )
        self.assertEqual(
            self.resolver.text_path(1750, "0000001750-26-000001", "generic_text_v1"),
            "text/sec/cik=1750/accession=0000001750-26-000001/generic_text_v1.txt",
        )
        self.assertEqual(
            self.resolver.gold_table_path("company", "run-123"),
            "gold/company/run_id=run-123/company.parquet",
        )
        self.assertEqual(
            self.resolver.snowflake_export_table_path("ticker_reference", "2026-04-22", "run-123"),
            "ticker_reference/business_date=2026-04-22/run_id=run-123/ticker_reference.parquet",
        )
        self.assertEqual(
            self.resolver.snowflake_export_run_manifest_path(
                workflow_name="bootstrap_recent_10",
                business_date="2026-04-22",
                run_id="run-123",
            ),
            "manifests/workflow_name=bootstrap_recent_10/business_date=2026-04-22/run_id=run-123/run_manifest.json",
        )

    def test_resolver_plans_default_and_special_manifest_paths(self) -> None:
        self.assertEqual(
            self.resolver.planned_manifest_paths(
                command_name="bootstrap-recent-10",
                command_path="bootstrap-recent-10",
                run_id="run-123",
                scope={},
            ),
            {
                "bronze": "runs/bootstrap-recent-10/run-123/manifest.json",
                "staging": "staging/runs/bootstrap-recent-10/run-123/manifest.json",
                "silver": "silver/sec/runs/bootstrap-recent-10/run-123/manifest.json",
                "gold": "gold/runs/bootstrap-recent-10/run-123/manifest.json",
                "artifacts": "artifacts/runs/bootstrap-recent-10/run-123/manifest.json",
            },
        )
        self.assertEqual(
            self.resolver.planned_manifest_paths(
                command_name="load-daily-form-index-for-date",
                command_path="load-daily-form-index-for-date",
                run_id="run-123",
                scope={"target_date": "2026-04-22"},
            ),
            {
                "bronze": "daily-index/date=2026-04-22/run-123/manifest.json",
                "staging": "staging/daily-index/date=2026-04-22/run-123/manifest.json",
                "artifacts": "artifacts/runs/load-daily-form-index-for-date/run-123/manifest.json",
            },
        )
        self.assertEqual(
            self.resolver.planned_manifest_paths(
                command_name="catch-up-daily-form-index",
                command_path="catch-up-daily-form-index",
                run_id="run-123",
                scope={"end_date": "2026-04-22"},
            ),
            {
                "bronze": "daily-index/catch-up/end-date=2026-04-22/run-123/manifest.json",
                "staging": "staging/daily-index/catch-up/end-date=2026-04-22/run-123/manifest.json",
                "artifacts": "artifacts/runs/catch-up-daily-form-index/run-123/manifest.json",
            },
        )


class CaptureSpecFactoryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.factory = CaptureSpecFactory(WarehousePathResolver(load_path_template_catalog()))

    def test_factory_builds_reference_submissions_daily_index_and_artifact_specs(self) -> None:
        reference = self.factory.reference("company_tickers_exchange", date(2026, 4, 22))
        self.assertEqual(reference.source_name, "company_tickers_exchange")
        self.assertTrue(reference.source_url.endswith("/files/company_tickers_exchange.json"))
        self.assertEqual(
            reference.relative_path,
            "reference/sec/company_tickers_exchange/2026/04/22/company_tickers_exchange.json",
        )

        cik_batches = self.factory.cik_universe_batches("run-123")
        self.assertEqual(cik_batches.source_name, "cik_universe_batches")
        self.assertEqual(
            cik_batches.relative_path,
            "reference/cik_universe/runs/run-123/cik_batches.jsonl",
        )

        main = self.factory.submissions_main(1750, date(2026, 4, 22))
        self.assertEqual(main.source_name, "submissions_main")
        self.assertTrue(main.source_url.endswith("/submissions/CIK0000001750.json"))
        self.assertEqual(
            main.relative_path,
            "submissions/sec/cik=1750/main/2026/04/22/CIK0000001750.json",
        )

        daily_index = self.factory.daily_index(date(2026, 4, 22))
        self.assertEqual(daily_index.source_name, "daily_index")
        self.assertTrue(daily_index.source_url.endswith("/daily-index/2026/QTR2/form.20260422.idx"))
        self.assertEqual(
            daily_index.relative_path,
            "daily_index/sec/2026/04/22/form.20260422.idx",
        )

        filing_index = self.factory.filing_index(1750, "0000001750-26-000001")
        self.assertEqual(filing_index.source_name, "filing_index")
        self.assertTrue(
            filing_index.source_url.endswith(
                "/1750/000000175026000001/000000175026000001-index.html"
            )
        )
        self.assertEqual(
            filing_index.relative_path,
            "filings/sec/cik=1750/accession=0000001750-26-000001/index/000000175026000001-index.html",
        )

        attachment = self.factory.filing_document(
            cik=1750,
            accession_number="0000001750-26-000001",
            document_name="nested/path/ex99.htm",
            is_primary=False,
        )
        self.assertEqual(attachment.source_name, "attachment")
        self.assertTrue(
            attachment.source_url.endswith(
                "/1750/000000175026000001/nested/path/ex99.htm"
            )
        )
        self.assertEqual(
            attachment.relative_path,
            "filings/sec/cik=1750/accession=0000001750-26-000001/attachments/ex99.htm",
        )

    def test_factory_builds_text_manifest_and_export_specs(self) -> None:
        self.assertEqual(
            self.factory.text_output(1750, "0000001750-26-000001", "generic_text_v1").relative_path,
            "text/sec/cik=1750/accession=0000001750-26-000001/generic_text_v1.txt",
        )
        self.assertEqual(
            self.factory.manifest_output(
                layer="bronze",
                command_name="bootstrap-recent-10",
                command_path="bootstrap-recent-10",
                run_id="run-123",
                scope={},
            ).relative_path,
            "runs/bootstrap-recent-10/run-123/manifest.json",
        )
        self.assertEqual(
            self.factory.gold_table_output("company", "run-123").relative_path,
            "gold/company/run_id=run-123/company.parquet",
        )
        self.assertEqual(
            self.factory.snowflake_export_table("company", "2026-04-22", "run-123").relative_path,
            "company/business_date=2026-04-22/run_id=run-123/company.parquet",
        )
        self.assertEqual(
            self.factory.snowflake_export_run_manifest(
                workflow_name="bootstrap_recent_10",
                business_date="2026-04-22",
                run_id="run-123",
            ).relative_path,
            "manifests/workflow_name=bootstrap_recent_10/business_date=2026-04-22/run_id=run-123/run_manifest.json",
        )

    def test_factory_rejects_unsupported_source(self) -> None:
        with self.assertRaises(WarehouseRuntimeError):
            self.factory.reference("unsupported_source", date(2026, 4, 22))


if __name__ == "__main__":
    unittest.main()
