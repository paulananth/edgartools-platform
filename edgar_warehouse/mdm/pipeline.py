"""MDM pipeline orchestrator.

Runs resolvers in the correct dependency order:
  1. Company   (no dependencies)
  2. Adviser   (links to Company via CIK)
  3. Security  (links to Company as issuer)
  4. Person    (links to Company via ownership filings)
  5. Fund      (links to Adviser)

Each phase reads from silver, resolves/creates MDM entities, and commits.
Graph sync runs last.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from sqlalchemy.orm import Session

from edgar_warehouse.mdm.graph import GraphSyncEngine, Neo4jGraphClient
from edgar_warehouse.mdm.resolvers.base import ResolverContext, SilverReader
from edgar_warehouse.mdm.resolvers import (
    AdviserResolver,
    CompanyResolver,
    FundResolver,
    PersonResolver,
    SecurityResolver,
)
from edgar_warehouse.mdm.rules import MDMRuleEngine


@dataclass
class PipelineStats:
    companies_processed: int = 0
    advisers_processed: int = 0
    persons_processed: int = 0
    securities_processed: int = 0
    funds_processed: int = 0
    graph_edges_synced: int = 0
    quarantined: int = 0
    sent_to_review: int = 0


@dataclass
class MDMPipeline:
    session: Session
    silver: SilverReader
    neo4j: Optional[Neo4jGraphClient] = None
    engine: MDMRuleEngine = field(init=False)
    run_id: str = ""

    def __post_init__(self) -> None:
        self.engine = MDMRuleEngine.load(self.session)

    def _ctx(self) -> ResolverContext:
        return ResolverContext(
            session=self.session,
            engine=self.engine,
            silver=self.silver,
            run_id=self.run_id,
        )

    def run_companies(self, limit: Optional[int] = None) -> int:
        ctx = self._ctx()
        resolver = CompanyResolver()
        sql = "SELECT * FROM sec_company"
        if limit:
            sql += f" LIMIT {int(limit)}"
        rows = self.silver.fetch(sql)
        processed = 0
        for row in rows:
            ticker = self._first(self.silver.fetch(
                "SELECT ticker, exchange FROM sec_company_ticker "
                "WHERE cik = ? ORDER BY source_rank NULLS LAST LIMIT 1",
                [row["cik"]],
            ))
            tracking = self._first(self.silver.fetch(
                "SELECT tracking_status FROM sec_tracked_universe WHERE cik = ?",
                [row["cik"]],
            ))
            resolver.resolve_one(ctx, "edgar_cik", row, ticker, tracking)
            processed += 1
        self.session.commit()
        return processed

    def run_advisers(self, limit: Optional[int] = None) -> int:
        ctx = self._ctx()
        resolver = AdviserResolver()
        sql = "SELECT * FROM sec_adv_filing"
        if limit:
            sql += f" LIMIT {int(limit)}"
        rows = self.silver.fetch(sql)
        processed = 0
        for row in rows:
            office = self._first(self.silver.fetch(
                "SELECT city, state_or_country FROM sec_adv_office "
                "WHERE accession_number = ? AND is_headquarters = TRUE LIMIT 1",
                [row["accession_number"]],
            ))
            resolver.resolve_one(ctx, "adv_filing", row, office,
                                 effective_date=row.get("effective_date"))
            processed += 1
        self.session.commit()
        return processed

    def run_all(self, limit: Optional[int] = None) -> PipelineStats:
        stats = PipelineStats()
        stats.companies_processed = self.run_companies(limit=limit)
        stats.advisers_processed = self.run_advisers(limit=limit)

        if self.neo4j is not None:
            sync = GraphSyncEngine.build(self.session, self.neo4j)
            stats.graph_edges_synced = sync.sync_pending()
            self.session.commit()
        return stats

    @staticmethod
    def _first(rows: list[dict]) -> Optional[dict]:
        return rows[0] if rows else None
