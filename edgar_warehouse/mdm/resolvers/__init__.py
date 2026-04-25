"""Per-domain MDM resolvers.

Each resolver:
  1. Reads source records from silver DuckDB
  2. Normalizes input attributes using MDMRuleEngine
  3. Matches against existing MDM entities via MatchPipeline
  4. Creates or updates mdm_entity + mdm_source_ref rows in PostgreSQL
  5. Stages attribute values into mdm_entity_attribute_stage
  6. Runs Priority Merge survivorship to compute golden record field values
  7. Writes the golden record to the domain table (mdm_company, mdm_adviser...)
  8. Inserts a mdm_change_log row for Snowflake export
"""
from edgar_warehouse.mdm.resolvers.base import BaseResolver, ResolverContext
from edgar_warehouse.mdm.resolvers.adviser import AdviserResolver
from edgar_warehouse.mdm.resolvers.company import CompanyResolver
from edgar_warehouse.mdm.resolvers.fund import FundResolver
from edgar_warehouse.mdm.resolvers.person import PersonResolver
from edgar_warehouse.mdm.resolvers.security import SecurityResolver

__all__ = [
    "BaseResolver",
    "ResolverContext",
    "AdviserResolver",
    "CompanyResolver",
    "FundResolver",
    "PersonResolver",
    "SecurityResolver",
]
