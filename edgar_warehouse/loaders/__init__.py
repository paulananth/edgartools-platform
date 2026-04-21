"""Pure SEC payload loaders split by source family."""

from edgar_warehouse.loaders.daily_index import stage_daily_index_filing_loader
from edgar_warehouse.loaders.reference_data import seed_universe_loader
from edgar_warehouse.loaders.submissions import (
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
