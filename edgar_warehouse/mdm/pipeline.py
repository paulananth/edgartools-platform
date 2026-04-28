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
    relationships_written: int = 0


def _derive_role(row: dict) -> str:
    if row.get("is_director"):
        return "director"
    if row.get("is_officer"):
        return "officer"
    if row.get("is_ten_percent_owner"):
        return "10pct_owner"
    return "other"


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

    def run_securities(self, limit: Optional[int] = None) -> int:
        ctx = self._ctx()
        resolver = SecurityResolver()
        sql = """
            SELECT DISTINCT t.accession_number, t.owner_index, t.txn_index,
                   t.security_title, f.cik AS issuer_cik
            FROM sec_ownership_non_derivative_txn t
            JOIN sec_company_filing f ON t.accession_number = f.accession_number
            WHERE t.security_title IS NOT NULL
        """
        if limit:
            sql += f" LIMIT {int(limit)}"
        rows = self.silver.fetch(sql)
        processed = 0
        for row in rows:
            issuer_entity_id = self._company_entity_id(row.get("issuer_cik"))
            resolver.resolve_one(ctx, "ownership_filing", row, issuer_entity_id)
            processed += 1
        self.session.commit()
        return processed

    def run_persons(self, limit: Optional[int] = None) -> int:
        ctx = self._ctx()
        resolver = PersonResolver()
        sql = """
            SELECT DISTINCT o.owner_cik, o.owner_name, o.officer_title,
                   o.is_director, o.is_officer, o.is_ten_percent_owner, o.is_other,
                   o.accession_number, o.owner_index, f.cik AS issuer_cik
            FROM sec_ownership_reporting_owner o
            JOIN sec_company_filing f ON o.accession_number = f.accession_number
            WHERE o.owner_name IS NOT NULL
        """
        if limit:
            sql += f" LIMIT {int(limit)}"
        rows = self.silver.fetch(sql)
        company_ciks = self._company_cik_set()
        processed = 0
        for row in rows:
            if row.get("owner_cik") in company_ciks:
                continue
            resolver.resolve_one(ctx, "ownership_filing", row,
                                 issuer_cik=row.get("issuer_cik"))
            processed += 1
        self.session.commit()
        return processed

    def run_funds(self, limit: Optional[int] = None) -> int:
        ctx = self._ctx()
        resolver = FundResolver()
        sql = "SELECT * FROM sec_adv_private_fund"
        if limit:
            sql += f" LIMIT {int(limit)}"
        rows = self.silver.fetch(sql)
        processed = 0
        for row in rows:
            adviser_entity_id = self._adviser_entity_id(row.get("accession_number"))
            resolver.resolve_one(ctx, "adv_filing", row, adviser_entity_id,
                                 effective_date=row.get("effective_date"))
            processed += 1
        self.session.commit()
        return processed

    def run_relationships(self, limit: Optional[int] = None) -> int:
        sync_engine = GraphSyncEngine.build(self.session, neo4j=None)
        written = 0

        # --- IS_INSIDER: person → company from Form 3/4/5 ---
        sql = """
            SELECT o.accession_number, o.owner_index, o.owner_cik, o.owner_name,
                   o.is_director, o.is_officer, o.is_ten_percent_owner, o.is_other,
                   o.officer_title,
                   f.cik AS issuer_cik, f.report_date AS period_of_report
            FROM sec_ownership_reporting_owner o
            JOIN sec_company_filing f ON o.accession_number = f.accession_number
        """
        if limit:
            sql += f" LIMIT {int(limit)}"
        company_ciks = self._company_cik_set()
        for row in self.silver.fetch(sql):
            owner_cik = row.get("owner_cik")
            if owner_cik in company_ciks:
                continue
            issuer_id = self._company_entity_id(row.get("issuer_cik"))
            person_id = self._person_entity_id(owner_cik, row.get("owner_name"))
            if issuer_id is None or person_id is None:
                continue
            sync_engine.record_relationship(
                rel_type_name="IS_INSIDER",
                source_entity_id=person_id,
                target_entity_id=issuer_id,
                properties={"role": _derive_role(row), "title": row.get("officer_title") or ""},
                effective_from=row.get("period_of_report"),
                source_system="ownership_filing",
                source_accession=row.get("accession_number"),
            )
            written += 1
        self.session.commit()

        # --- IS_ENTITY_OF: adviser → company (already linked by AdviserResolver) ---
        for adviser_id, company_id in self._adviser_company_pairs():
            sync_engine.record_relationship(
                rel_type_name="IS_ENTITY_OF",
                source_entity_id=adviser_id,
                target_entity_id=company_id,
                source_system="adv_filing",
            )
            written += 1
        self.session.commit()

        # --- IS_PERSON_OF: individual adviser → person (CIK match) ---
        for adviser_id, person_id in self._adviser_person_pairs():
            sync_engine.record_relationship(
                rel_type_name="IS_PERSON_OF",
                source_entity_id=adviser_id,
                target_entity_id=person_id,
                source_system="adv_filing",
            )
            written += 1
        self.session.commit()

        # --- MANAGES_FUND + ISSUED_BY (keep existing backfill) ---
        from edgar_warehouse.mdm.graph import backfill_relationship_instances
        backfill_limit = limit if limit is not None else 10_000
        backfill_relationship_instances(self.session, neo4j=None, limit=backfill_limit)

        return written

    def run_all(self, limit: Optional[int] = None) -> PipelineStats:
        stats = PipelineStats()
        stats.companies_processed = self.run_companies(limit=limit)
        stats.advisers_processed = self.run_advisers(limit=limit)
        stats.securities_processed = self.run_securities(limit=limit)
        stats.persons_processed = self.run_persons(limit=limit)
        stats.funds_processed = self.run_funds(limit=limit)
        stats.relationships_written = self.run_relationships(limit=limit)
        if self.neo4j is not None:
            sync = GraphSyncEngine.build(self.session, self.neo4j)
            stats.graph_edges_synced = sync.sync_pending()
            self.session.commit()
        return stats

    def _company_cik_set(self) -> set:
        from edgar_warehouse.mdm.database import MdmCompany
        from sqlalchemy import select
        return set(self.session.scalars(
            select(MdmCompany.cik).where(MdmCompany.cik.isnot(None))
        ))

    def _company_entity_id(self, cik) -> Optional[str]:
        if cik is None:
            return None
        from edgar_warehouse.mdm.database import MdmCompany
        from sqlalchemy import select
        return self.session.scalar(
            select(MdmCompany.entity_id).where(MdmCompany.cik == int(cik))
        )

    def _person_entity_id(self, owner_cik, owner_name) -> Optional[str]:
        from edgar_warehouse.mdm.database import MdmPerson
        from sqlalchemy import select
        if owner_cik is not None:
            result = self.session.scalar(
                select(MdmPerson.entity_id).where(MdmPerson.owner_cik == int(owner_cik))
            )
            if result:
                return result
        if owner_name:
            return self.session.scalar(
                select(MdmPerson.entity_id).where(MdmPerson.canonical_name == owner_name)
            )
        return None

    def _adviser_entity_id(self, accession_number) -> Optional[str]:
        if accession_number is None:
            return None
        from edgar_warehouse.mdm.database import MdmEntity, MdmSourceRef
        from sqlalchemy import select
        return self.session.scalar(
            select(MdmSourceRef.entity_id)
            .join(MdmEntity, MdmEntity.entity_id == MdmSourceRef.entity_id)
            .where(MdmSourceRef.source_system == "adv_filing")
            .where(MdmSourceRef.source_id == accession_number)
            .where(MdmEntity.entity_type == "adviser")
        )

    def _adviser_company_pairs(self):
        from edgar_warehouse.mdm.database import MdmAdviser
        from sqlalchemy import select
        return self.session.execute(
            select(MdmAdviser.entity_id, MdmAdviser.linked_company_entity_id)
            .where(MdmAdviser.linked_company_entity_id.isnot(None))
        ).all()

    def _adviser_person_pairs(self):
        from edgar_warehouse.mdm.database import MdmAdviser, MdmPerson
        from sqlalchemy import select
        return self.session.execute(
            select(MdmAdviser.entity_id, MdmPerson.entity_id)
            .join(MdmPerson, MdmPerson.owner_cik == MdmAdviser.cik)
            .where(MdmAdviser.cik.isnot(None))
            .where(MdmAdviser.linked_company_entity_id.is_(None))
        ).all()

    @staticmethod
    def _first(rows: list[dict]) -> Optional[dict]:
        return rows[0] if rows else None
