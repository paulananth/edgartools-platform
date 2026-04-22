"""Pure SEC payload loaders split by Bronze source family."""

from edgar_warehouse.loaders.bronze_daily_index_extractors import stage_daily_index_filing_loader
from edgar_warehouse.loaders.bronze_reference_extractors import seed_universe_loader
from edgar_warehouse.loaders.bronze_submission_extractors import (
    stage_address_loader,
    stage_company_loader,
    stage_former_name_loader,
    stage_manifest_loader,
    stage_pagination_filing_loader,
    stage_recent_filing_loader,
)

__all__ = [
    "seed_universe_loader",
    "stage_address_loader",
    "stage_company_loader",
    "stage_daily_index_filing_loader",
    "stage_former_name_loader",
    "stage_manifest_loader",
    "stage_pagination_filing_loader",
    "stage_recent_filing_loader",
]
