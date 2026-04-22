"""Warehouse path templates and capture spec planning."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from functools import lru_cache
from importlib import resources
from string import Formatter
from typing import Iterable

from edgar_warehouse.application.errors import WarehouseRuntimeError
from edgar_warehouse.infrastructure.sec_client import (
    build_company_tickers_exchange_url,
    build_company_tickers_url,
    build_daily_index_url,
    build_filing_document_url,
    build_filing_index_url,
    build_submission_pagination_url,
    build_submissions_url,
)
from edgar_warehouse.infrastructure.object_storage import sanitize_filename

_FORMATTER = Formatter()
_ALLOWED_TEMPLATE_TOKENS = frozenset(
    {
        "accession_number",
        "business_date",
        "cik",
        "command_path",
        "date_path",
        "document_name",
        "end_date",
        "run_id",
        "section",
        "table_name",
        "table_path",
        "text_version",
        "workflow_name",
    }
)
_DEFAULT_MANIFEST_COMMANDS = frozenset(
    {
        "bootstrap-recent-10",
        "bootstrap-full",
        "bootstrap-batch",
        "daily-incremental",
        "targeted-resync",
        "full-reconcile",
    }
)
_REFERENCE_SOURCES = frozenset({"company_tickers", "company_tickers_exchange"})
_REQUIRED_TEMPLATE_KEYS = frozenset(
    {
        "reference.company_tickers.path",
        "reference.company_tickers_exchange.path",
        "reference.cik_universe_batches.path",
        "submissions.main.filename",
        "submissions.main.path",
        "submissions.pagination.path",
        "daily_index.filename",
        "daily_index.path",
        "filings.index.filename",
        "filings.index.path",
        "filings.document.path",
        "text.filename",
        "text.path",
        "manifest.default.bronze.path",
        "manifest.default.staging.path",
        "manifest.default.silver.path",
        "manifest.default.gold.path",
        "manifest.default.artifacts.path",
        "manifest.load_daily_form_index_for_date.bronze.path",
        "manifest.load_daily_form_index_for_date.staging.path",
        "manifest.catch_up_daily_form_index.bronze.path",
        "manifest.catch_up_daily_form_index.staging.path",
        "gold.table.filename",
        "gold.table.path",
        "snowflake_export.table.filename",
        "snowflake_export.table.path",
        "snowflake_export.run_manifest.path",
    }
)


@dataclass(frozen=True)
class CaptureSpec:
    """A planned warehouse write path, optionally backed by a remote source."""

    source_name: str
    relative_path: str
    source_url: str | None = None


@dataclass(frozen=True)
class PathTemplateCatalog:
    """Validated warehouse path templates."""

    templates: dict[str, str]

    @classmethod
    def from_text(cls, text: str) -> "PathTemplateCatalog":
        templates = _parse_properties(text)
        missing = sorted(_REQUIRED_TEMPLATE_KEYS - set(templates))
        if missing:
            raise WarehouseRuntimeError(
                "Missing warehouse path templates: " + ", ".join(missing)
            )
        for key, value in templates.items():
            _validate_template(key, value)
        return cls(templates=templates)

    @classmethod
    def load_default(cls) -> "PathTemplateCatalog":
        content = (
            resources.files("edgar_warehouse.config")
            .joinpath("warehouse_paths.properties")
            .read_text(encoding="utf-8")
        )
        return cls.from_text(content)

    def get(self, key: str) -> str:
        try:
            return self.templates[key]
        except KeyError as exc:
            raise WarehouseRuntimeError(f"Missing warehouse path template: {key}") from exc


class WarehousePathResolver:
    """Typed accessors for warehouse relative path contracts."""

    def __init__(self, catalog: PathTemplateCatalog) -> None:
        self._catalog = catalog

    def reference_snapshot_path(self, source_name: str, fetch_date: date) -> str:
        if source_name not in _REFERENCE_SOURCES:
            raise WarehouseRuntimeError(f"Unsupported reference source: {source_name}")
        return self._render(
            f"reference.{source_name}.path",
            date_path=_date_path(fetch_date),
        )

    def cik_universe_batches_path(self, run_id: str) -> str:
        return self._render("reference.cik_universe_batches.path", run_id=run_id)

    def submissions_main_filename(self, cik: int) -> str:
        return self._render("submissions.main.filename", cik=cik)

    def submissions_main_path(self, cik: int, fetch_date: date) -> str:
        return self._render(
            "submissions.main.path",
            cik=cik,
            date_path=_date_path(fetch_date),
            document_name=self.submissions_main_filename(cik),
        )

    def submissions_pagination_path(self, cik: int, fetch_date: date, document_name: str) -> str:
        return self._render(
            "submissions.pagination.path",
            cik=cik,
            date_path=_date_path(fetch_date),
            document_name=document_name,
        )

    def daily_index_filename(self, target_date: date) -> str:
        return self._render("daily_index.filename", business_date=target_date.strftime("%Y%m%d"))

    def daily_index_path(self, target_date: date) -> str:
        return self._render(
            "daily_index.path",
            date_path=_date_path(target_date),
            document_name=self.daily_index_filename(target_date),
        )

    def filing_index_filename(self, accession_number: str) -> str:
        accession_digits = accession_number.replace("-", "")
        return self._render("filings.index.filename", accession_number=accession_digits)

    def filing_index_path(self, cik: int, accession_number: str) -> str:
        return self._render(
            "filings.index.path",
            cik=cik,
            accession_number=accession_number,
            document_name=self.filing_index_filename(accession_number),
        )

    def filing_document_path(
        self,
        *,
        cik: int,
        accession_number: str,
        section: str,
        document_name: str,
    ) -> str:
        return self._render(
            "filings.document.path",
            cik=cik,
            accession_number=accession_number,
            section=section,
            document_name=sanitize_filename(document_name),
        )

    def text_filename(self, text_version: str) -> str:
        return self._render("text.filename", text_version=text_version)

    def text_path(self, cik: int, accession_number: str, text_version: str) -> str:
        return self._render(
            "text.path",
            cik=cik,
            accession_number=accession_number,
            document_name=self.text_filename(text_version),
        )

    def planned_manifest_paths(
        self,
        *,
        command_name: str,
        command_path: str,
        run_id: str,
        scope: dict[str, str],
    ) -> dict[str, str]:
        default_tokens = {"command_path": command_path, "run_id": run_id}
        if command_name in _DEFAULT_MANIFEST_COMMANDS:
            return {
                "bronze": self._render("manifest.default.bronze.path", **default_tokens),
                "staging": self._render("manifest.default.staging.path", **default_tokens),
                "silver": self._render("manifest.default.silver.path", **default_tokens),
                "gold": self._render("manifest.default.gold.path", **default_tokens),
                "artifacts": self._render("manifest.default.artifacts.path", **default_tokens),
            }
        if command_name == "seed-universe":
            return {
                "bronze": self._render("manifest.default.bronze.path", **default_tokens),
                "staging": self._render("manifest.default.staging.path", **default_tokens),
                "artifacts": self._render("manifest.default.artifacts.path", **default_tokens),
            }
        if command_name == "load-daily-form-index-for-date":
            business_date = str(scope["target_date"])
            return {
                "bronze": self._render(
                    "manifest.load_daily_form_index_for_date.bronze.path",
                    business_date=business_date,
                    run_id=run_id,
                ),
                "staging": self._render(
                    "manifest.load_daily_form_index_for_date.staging.path",
                    business_date=business_date,
                    run_id=run_id,
                ),
                "artifacts": self._render("manifest.default.artifacts.path", **default_tokens),
            }
        if command_name == "catch-up-daily-form-index":
            end_date = str(scope["end_date"])
            return {
                "bronze": self._render(
                    "manifest.catch_up_daily_form_index.bronze.path",
                    end_date=end_date,
                    run_id=run_id,
                ),
                "staging": self._render(
                    "manifest.catch_up_daily_form_index.staging.path",
                    end_date=end_date,
                    run_id=run_id,
                ),
                "artifacts": self._render("manifest.default.artifacts.path", **default_tokens),
            }
        raise WarehouseRuntimeError(f"Unsupported warehouse command: {command_name}")

    def gold_table_path(self, table_name: str, run_id: str) -> str:
        document_name = self._render("gold.table.filename", table_name=table_name)
        return self._render(
            "gold.table.path",
            table_name=table_name,
            run_id=run_id,
            document_name=document_name,
        )

    def snowflake_export_table_path(self, table_path: str, business_date: str, run_id: str) -> str:
        document_name = self._render("snowflake_export.table.filename", table_path=table_path)
        return self._render(
            "snowflake_export.table.path",
            table_path=table_path,
            business_date=business_date,
            run_id=run_id,
            document_name=document_name,
        )

    def snowflake_export_run_manifest_path(
        self,
        *,
        workflow_name: str,
        business_date: str,
        run_id: str,
    ) -> str:
        return self._render(
            "snowflake_export.run_manifest.path",
            workflow_name=workflow_name,
            business_date=business_date,
            run_id=run_id,
        )

    def _render(self, key: str, **tokens: object) -> str:
        template = self._catalog.get(key)
        try:
            return template.format(**tokens)
        except KeyError as exc:
            raise WarehouseRuntimeError(
                f"Missing template token {exc.args[0]!r} while rendering {key}"
            ) from exc


class CaptureSpecFactory:
    """Factory helpers for source-backed capture and output path planning."""

    def __init__(self, resolver: WarehousePathResolver) -> None:
        self._resolver = resolver

    def reference(self, source_name: str, fetch_date: date) -> CaptureSpec:
        if source_name == "company_tickers":
            source_url = build_company_tickers_url()
        elif source_name == "company_tickers_exchange":
            source_url = build_company_tickers_exchange_url()
        else:
            raise WarehouseRuntimeError(f"Unsupported reference source: {source_name}")
        return CaptureSpec(
            source_name=source_name,
            source_url=source_url,
            relative_path=self._resolver.reference_snapshot_path(source_name, fetch_date),
        )

    def references(self, fetch_date: date, source_names: Iterable[str] | None = None) -> list[CaptureSpec]:
        selected = list(source_names or ("company_tickers", "company_tickers_exchange"))
        return [self.reference(source_name, fetch_date) for source_name in selected]

    def cik_universe_batches(self, run_id: str) -> CaptureSpec:
        return CaptureSpec(
            source_name="cik_universe_batches",
            relative_path=self._resolver.cik_universe_batches_path(run_id),
        )

    def submissions_main(self, cik: int, fetch_date: date) -> CaptureSpec:
        return CaptureSpec(
            source_name="submissions_main",
            source_url=build_submissions_url(cik),
            relative_path=self._resolver.submissions_main_path(cik, fetch_date),
        )

    def submissions_pagination(self, cik: int, file_name: str, fetch_date: date) -> CaptureSpec:
        return CaptureSpec(
            source_name="submissions_pagination",
            source_url=build_submission_pagination_url(file_name),
            relative_path=self._resolver.submissions_pagination_path(cik, fetch_date, file_name),
        )

    def daily_index(self, target_date: date) -> CaptureSpec:
        return CaptureSpec(
            source_name="daily_index",
            source_url=build_daily_index_url(target_date),
            relative_path=self._resolver.daily_index_path(target_date),
        )

    def filing_index(self, cik: int, accession_number: str) -> CaptureSpec:
        accession_digits = accession_number.replace("-", "")
        return CaptureSpec(
            source_name="filing_index",
            source_url=build_filing_index_url(cik, accession_digits),
            relative_path=self._resolver.filing_index_path(cik, accession_number),
        )

    def filing_document(
        self,
        *,
        cik: int,
        accession_number: str,
        document_name: str,
        is_primary: bool,
    ) -> CaptureSpec:
        accession_digits = accession_number.replace("-", "")
        return CaptureSpec(
            source_name="filing_document" if is_primary else "attachment",
            source_url=build_filing_document_url(cik, accession_digits, document_name),
            relative_path=self._resolver.filing_document_path(
                cik=cik,
                accession_number=accession_number,
                section="primary" if is_primary else "attachments",
                document_name=document_name,
            ),
        )

    def text_output(self, cik: int, accession_number: str, text_version: str) -> CaptureSpec:
        return CaptureSpec(
            source_name="filing_text",
            relative_path=self._resolver.text_path(cik, accession_number, text_version),
        )

    def manifest_output(
        self,
        *,
        layer: str,
        command_name: str,
        command_path: str,
        run_id: str,
        scope: dict[str, str],
    ) -> CaptureSpec:
        paths = self._resolver.planned_manifest_paths(
            command_name=command_name,
            command_path=command_path,
            run_id=run_id,
            scope=scope,
        )
        return CaptureSpec(source_name=f"{layer}_manifest", relative_path=paths[layer])

    def gold_table_output(self, table_name: str, run_id: str) -> CaptureSpec:
        return CaptureSpec(
            source_name="gold_table",
            relative_path=self._resolver.gold_table_path(table_name, run_id),
        )

    def snowflake_export_table(self, table_path: str, business_date: str, run_id: str) -> CaptureSpec:
        return CaptureSpec(
            source_name="snowflake_export_table",
            relative_path=self._resolver.snowflake_export_table_path(table_path, business_date, run_id),
        )

    def snowflake_export_run_manifest(
        self,
        *,
        workflow_name: str,
        business_date: str,
        run_id: str,
    ) -> CaptureSpec:
        return CaptureSpec(
            source_name="snowflake_export_run_manifest",
            relative_path=self._resolver.snowflake_export_run_manifest_path(
                workflow_name=workflow_name,
                business_date=business_date,
                run_id=run_id,
            ),
        )


@lru_cache(maxsize=1)
def default_path_resolver() -> WarehousePathResolver:
    return WarehousePathResolver(load_path_template_catalog())


@lru_cache(maxsize=1)
def default_capture_spec_factory() -> CaptureSpecFactory:
    return CaptureSpecFactory(default_path_resolver())


@lru_cache(maxsize=1)
def load_path_template_catalog() -> PathTemplateCatalog:
    return PathTemplateCatalog.load_default()


def _date_path(target_date: date) -> str:
    return target_date.strftime("%Y/%m/%d")


def _parse_properties(text: str) -> dict[str, str]:
    templates: dict[str, str] = {}
    for lineno, raw_line in enumerate(text.splitlines(), start=1):
        line = raw_line.strip()
        if not line or line.startswith("#") or line.startswith(";"):
            continue
        separator = "=" if "=" in line else ":" if ":" in line else None
        if separator is None:
            raise WarehouseRuntimeError(f"Invalid properties line {lineno}: {raw_line}")
        key, value = line.split(separator, 1)
        key = key.strip()
        value = value.strip()
        if not key:
            raise WarehouseRuntimeError(f"Invalid empty properties key on line {lineno}")
        if key in templates:
            raise WarehouseRuntimeError(f"Duplicate warehouse path template: {key}")
        templates[key] = value
    return templates


def _validate_template(key: str, value: str) -> None:
    try:
        segments = list(_FORMATTER.parse(value))
    except ValueError as exc:
        raise WarehouseRuntimeError(f"Invalid warehouse path template {key}: {exc}") from exc
    for _literal, field_name, _format_spec, _conversion in segments:
        if field_name is None:
            continue
        if not field_name:
            raise WarehouseRuntimeError(f"Positional fields are not allowed in warehouse path template {key}")
        if field_name not in _ALLOWED_TEMPLATE_TOKENS:
            raise WarehouseRuntimeError(
                f"Unknown template token {field_name!r} in warehouse path template {key}"
            )
