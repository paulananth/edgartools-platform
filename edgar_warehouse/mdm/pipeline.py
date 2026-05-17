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

import json
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Iterable, Optional

from sqlalchemy import func, select
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

RELATIONSHIP_TYPES = (
    "IS_INSIDER",
    "HOLDS",
    "ISSUED_BY",
    "IS_ENTITY_OF",
    "MANAGES_FUND",
    "IS_PERSON_OF",
)


@dataclass
class PipelineStats:
    companies_processed: int = 0
    advisers_processed: int = 0
    persons_processed: int = 0
    securities_processed: int = 0
    funds_processed: int = 0
    graph_nodes_synced: int = 0
    graph_edges_synced: int = 0
    quarantined: int = 0
    sent_to_review: int = 0
    relationships_written: int = 0
    relationship_counts_by_type: dict[str, dict[str, int | None]] = field(default_factory=dict)


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
                "SELECT tracking_status FROM sec_company_sync_state WHERE cik = ?",
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
        summary = self.derive_relationships(target_per_type=limit)
        return sum(int(item["inserted"] or 0) for item in summary.values())

    def derive_relationships(
        self,
        *,
        target_per_type: Optional[int] = None,
        relationship_types: Optional[Iterable[str]] = None,
    ) -> dict[str, dict[str, int | None]]:
        """Create relationship instances until each requested type reaches target_per_type.

        Existing active relationships count toward the target. Returned counts
        are per type so operators can see source shortfalls without inspecting
        MDM tables directly.
        """
        sync_engine = GraphSyncEngine.build(self.session, neo4j=None)
        requested_types = self._relationship_type_names(relationship_types)
        summary: dict[str, dict[str, int | None]] = {}
        for rel_type_name in requested_types:
            existing = self._relationship_count(rel_type_name)
            remaining = None
            if target_per_type is not None:
                remaining = max(int(target_per_type) - existing, 0)
            inserted = 0
            skipped_corporate = 0
            skipped_unresolved_source = 0
            skipped_unresolved_target = 0
            skipped_existing = 0
            if remaining is None or remaining > 0:
                (inserted, skipped_corporate, skipped_unresolved_source,
                 skipped_unresolved_target, skipped_existing) = \
                    self._derive_relationship_type(sync_engine, rel_type_name, remaining)
            summary[rel_type_name] = {
                "existing":                  existing,
                "inserted":                  inserted,
                "skipped":                   (skipped_corporate + skipped_unresolved_source
                                              + skipped_unresolved_target + skipped_existing),
                "skipped_corporate":         skipped_corporate,
                "skipped_unresolved_source": skipped_unresolved_source,
                "skipped_unresolved_target": skipped_unresolved_target,
                "skipped_existing":          skipped_existing,
                "target":                    target_per_type,
                "total":                     existing + inserted,
            }
        self.session.commit()
        return summary

    def _derive_relationship_type(
        self,
        sync_engine: GraphSyncEngine,
        rel_type_name: str,
        remaining: Optional[int],
    ) -> tuple[int, int, int, int, int]:
        if rel_type_name == "IS_INSIDER":
            return self._derive_is_insider(sync_engine, remaining)
        if rel_type_name == "HOLDS":
            return self._derive_holds(sync_engine, remaining)
        if rel_type_name == "ISSUED_BY":
            return self._derive_issued_by(sync_engine, remaining)
        if rel_type_name == "IS_ENTITY_OF":
            return self._derive_is_entity_of(sync_engine, remaining)
        if rel_type_name == "MANAGES_FUND":
            return self._derive_manages_fund(sync_engine, remaining)
        if rel_type_name == "IS_PERSON_OF":
            return self._derive_is_person_of(sync_engine, remaining)
        raise KeyError(f"Unknown relationship type '{rel_type_name}'")

    def _derive_is_insider(self, sync_engine: GraphSyncEngine, remaining: Optional[int]) -> tuple[int, int, int, int, int]:
        sql = """
            SELECT o.accession_number, o.owner_index, o.owner_cik, o.owner_name,
                   o.is_director, o.is_officer, o.is_ten_percent_owner, o.is_other,
                   o.officer_title,
                   f.cik AS issuer_cik, f.report_date AS period_of_report
            FROM sec_ownership_reporting_owner o
            JOIN sec_company_filing f ON o.accession_number = f.accession_number
        """
        company_ciks = self._company_cik_set()
        inserted = 0
        skipped_corporate = 0
        skipped_unresolved_source = 0
        skipped_unresolved_target = 0
        skipped_existing = 0
        for row in self.silver.fetch(sql):
            owner_cik = row.get("owner_cik")
            if owner_cik in company_ciks:
                skipped_corporate += 1
                print(json.dumps({
                    "event": "mdm_relationship_skip",
                    "rel_type": "IS_INSIDER",
                    "reason": "corporate",
                    "owner_cik": owner_cik,
                    "ts": datetime.now(timezone.utc).isoformat(),
                }), file=sys.stderr, flush=True)
                continue
            person_id = self._person_entity_id(owner_cik, row.get("owner_name"))
            if person_id is None:
                skipped_unresolved_source += 1
                print(json.dumps({
                    "event": "mdm_relationship_skip",
                    "rel_type": "IS_INSIDER",
                    "reason": "unresolved_source",
                    "owner_cik": owner_cik,
                    "owner_name": row.get("owner_name"),
                    "ts": datetime.now(timezone.utc).isoformat(),
                }), file=sys.stderr, flush=True)
                continue
            issuer_id = self._company_entity_id(row.get("issuer_cik"))
            if issuer_id is None:
                skipped_unresolved_target += 1
                print(json.dumps({
                    "event": "mdm_relationship_skip",
                    "rel_type": "IS_INSIDER",
                    "reason": "unresolved_target",
                    "issuer_cik": row.get("issuer_cik"),
                    "ts": datetime.now(timezone.utc).isoformat(),
                }), file=sys.stderr, flush=True)
                continue
            _rel, created = sync_engine.ensure_relationship(
                rel_type_name="IS_INSIDER",
                source_entity_id=person_id,
                target_entity_id=issuer_id,
                properties={"role": _derive_role(row), "title": row.get("officer_title") or ""},
                effective_from=row.get("period_of_report"),
                source_system="ownership_filing",
                source_accession=row.get("accession_number"),
            )
            if created:
                inserted += 1
            else:
                skipped_existing += 1
                print(json.dumps({
                    "event": "mdm_relationship_skip",
                    "rel_type": "IS_INSIDER",
                    "reason": "existing",
                    "source_entity_id": person_id,
                    "target_entity_id": issuer_id,
                    "ts": datetime.now(timezone.utc).isoformat(),
                }), file=sys.stderr, flush=True)
            if remaining is not None and inserted >= remaining:
                break
        return inserted, skipped_corporate, skipped_unresolved_source, skipped_unresolved_target, skipped_existing

    def _derive_holds(self, sync_engine: GraphSyncEngine, remaining: Optional[int]) -> tuple[int, int, int, int, int]:
        sql = """
            SELECT t.accession_number, t.owner_index, t.txn_index,
                   t.security_title, t.transaction_date, t.shares_owned_after,
                   t.ownership_direct_indirect,
                   o.owner_cik, o.owner_name,
                   f.cik AS issuer_cik
            FROM sec_ownership_non_derivative_txn t
            JOIN sec_ownership_reporting_owner o
              ON t.accession_number = o.accession_number
             AND t.owner_index = o.owner_index
            JOIN sec_company_filing f ON t.accession_number = f.accession_number
            WHERE t.security_title IS NOT NULL
        """
        company_ciks = self._company_cik_set()
        inserted = 0
        skipped_corporate = 0
        skipped_unresolved_source = 0
        skipped_unresolved_target = 0
        skipped_existing = 0
        for row in self.silver.fetch(sql):
            owner_cik = row.get("owner_cik")
            if owner_cik in company_ciks:
                skipped_corporate += 1
                print(json.dumps({
                    "event": "mdm_relationship_skip",
                    "rel_type": "HOLDS",
                    "reason": "corporate",
                    "owner_cik": owner_cik,
                    "ts": datetime.now(timezone.utc).isoformat(),
                }), file=sys.stderr, flush=True)
                continue
            person_id = self._person_entity_id(owner_cik, row.get("owner_name"))
            if person_id is None:
                skipped_unresolved_source += 1
                print(json.dumps({
                    "event": "mdm_relationship_skip",
                    "rel_type": "HOLDS",
                    "reason": "unresolved_source",
                    "owner_cik": owner_cik,
                    "owner_name": row.get("owner_name"),
                    "ts": datetime.now(timezone.utc).isoformat(),
                }), file=sys.stderr, flush=True)
                continue
            security_id = self._security_entity_id(row)
            if security_id is None:
                skipped_unresolved_target += 1
                print(json.dumps({
                    "event": "mdm_relationship_skip",
                    "rel_type": "HOLDS",
                    "reason": "unresolved_target",
                    "security_title": row.get("security_title"),
                    "issuer_cik": row.get("issuer_cik"),
                    "ts": datetime.now(timezone.utc).isoformat(),
                }), file=sys.stderr, flush=True)
                continue
            properties = {
                "shares_owned": self._json_property(row.get("shares_owned_after")),
                "direct_indirect": row.get("ownership_direct_indirect"),
                "as_of_date": self._json_property(row.get("transaction_date")),
            }
            _rel, created = sync_engine.ensure_relationship(
                rel_type_name="HOLDS",
                source_entity_id=person_id,
                target_entity_id=security_id,
                properties={k: v for k, v in properties.items() if v is not None},
                effective_from=row.get("transaction_date"),
                source_system="ownership_filing",
                source_accession=row.get("accession_number"),
            )
            if created:
                inserted += 1
            else:
                skipped_existing += 1
                print(json.dumps({
                    "event": "mdm_relationship_skip",
                    "rel_type": "HOLDS",
                    "reason": "existing",
                    "source_entity_id": person_id,
                    "target_entity_id": security_id,
                    "ts": datetime.now(timezone.utc).isoformat(),
                }), file=sys.stderr, flush=True)
            if remaining is not None and inserted >= remaining:
                break
        return inserted, skipped_corporate, skipped_unresolved_source, skipped_unresolved_target, skipped_existing

    def _derive_is_entity_of(self, sync_engine: GraphSyncEngine, remaining: Optional[int]) -> tuple[int, int, int, int, int]:
        inserted = 0
        skipped_corporate = 0
        skipped_unresolved_source = 0
        skipped_unresolved_target = 0
        skipped_existing = 0
        for adviser_id, company_id in self._adviser_company_pairs():
            _rel, created = sync_engine.ensure_relationship(
                rel_type_name="IS_ENTITY_OF",
                source_entity_id=adviser_id,
                target_entity_id=company_id,
                source_system="adv_filing",
            )
            inserted += 1 if created else 0
            skipped_existing += 0 if created else 1
            if remaining is not None and inserted >= remaining:
                break
        return inserted, skipped_corporate, skipped_unresolved_source, skipped_unresolved_target, skipped_existing

    def _derive_is_person_of(self, sync_engine: GraphSyncEngine, remaining: Optional[int]) -> tuple[int, int, int, int, int]:
        inserted = 0
        skipped_corporate = 0
        skipped_unresolved_source = 0
        skipped_unresolved_target = 0
        skipped_existing = 0
        for adviser_id, person_id in self._adviser_person_pairs():
            _rel, created = sync_engine.ensure_relationship(
                rel_type_name="IS_PERSON_OF",
                source_entity_id=adviser_id,
                target_entity_id=person_id,
                source_system="adv_filing",
            )
            inserted += 1 if created else 0
            skipped_existing += 0 if created else 1
            if remaining is not None and inserted >= remaining:
                break
        return inserted, skipped_corporate, skipped_unresolved_source, skipped_unresolved_target, skipped_existing

    def _derive_manages_fund(self, sync_engine: GraphSyncEngine, remaining: Optional[int]) -> tuple[int, int, int, int, int]:
        from edgar_warehouse.mdm.database import MdmFund

        inserted = 0
        skipped_corporate = 0
        skipped_unresolved_source = 0
        skipped_unresolved_target = 0
        skipped_existing = 0
        for fund in self.session.scalars(
            select(MdmFund).where(MdmFund.adviser_entity_id.isnot(None))
        ):
            _rel, created = sync_engine.ensure_relationship(
                rel_type_name="MANAGES_FUND",
                source_entity_id=fund.adviser_entity_id,
                target_entity_id=fund.entity_id,
                source_system="mdm_backfill",
            )
            inserted += 1 if created else 0
            skipped_existing += 0 if created else 1
            if remaining is not None and inserted >= remaining:
                break
        return inserted, skipped_corporate, skipped_unresolved_source, skipped_unresolved_target, skipped_existing

    def _derive_issued_by(self, sync_engine: GraphSyncEngine, remaining: Optional[int]) -> tuple[int, int, int, int, int]:
        from edgar_warehouse.mdm.database import MdmSecurity

        inserted = 0
        skipped_corporate = 0
        skipped_unresolved_source = 0
        skipped_unresolved_target = 0
        skipped_existing = 0
        for security in self.session.scalars(
            select(MdmSecurity).where(MdmSecurity.issuer_entity_id.isnot(None))
        ):
            _rel, created = sync_engine.ensure_relationship(
                rel_type_name="ISSUED_BY",
                source_entity_id=security.entity_id,
                target_entity_id=security.issuer_entity_id,
                source_system="mdm_backfill",
            )
            inserted += 1 if created else 0
            skipped_existing += 0 if created else 1
            if remaining is not None and inserted >= remaining:
                break
        return inserted, skipped_corporate, skipped_unresolved_source, skipped_unresolved_target, skipped_existing

    def run_all(self, limit: Optional[int] = None) -> PipelineStats:
        stats = PipelineStats()
        stats.companies_processed = self.run_companies(limit=limit)
        stats.advisers_processed = self.run_advisers(limit=limit)
        stats.securities_processed = self.run_securities(limit=limit)
        stats.persons_processed = self.run_persons(limit=limit)
        stats.funds_processed = self.run_funds(limit=limit)
        stats.relationship_counts_by_type = self.derive_relationships(target_per_type=limit)
        stats.relationships_written = sum(
            int(item["inserted"] or 0) for item in stats.relationship_counts_by_type.values()
        )
        if self.neo4j is not None:
            sync = GraphSyncEngine.build(self.session, self.neo4j)
            stats.graph_nodes_synced = sync.sync_entities(limit=limit)
            stats.graph_edges_synced = sync.sync_pending(limit_per_type=limit)
            self.session.commit()
        return stats

    def _relationship_type_names(self, relationship_types: Optional[Iterable[str]]) -> list[str]:
        if relationship_types is None:
            return list(RELATIONSHIP_TYPES)
        requested = [name.strip().upper() for name in relationship_types if name and name.strip()]
        unknown = sorted(set(requested) - set(RELATIONSHIP_TYPES))
        if unknown:
            raise KeyError(f"Unknown relationship type(s): {', '.join(unknown)}")
        return requested

    def _relationship_count(self, rel_type_name: str) -> int:
        from edgar_warehouse.mdm.database import MdmRelationshipInstance, MdmRelationshipType

        return int(
            self.session.scalar(
                select(func.count(MdmRelationshipInstance.instance_id))
                .join(MdmRelationshipType)
                .where(
                    MdmRelationshipType.rel_type_name == rel_type_name,
                    MdmRelationshipInstance.is_active == True,
                )
            )
            or 0
        )

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

    def _security_entity_id(self, txn_row: dict) -> Optional[str]:
        from edgar_warehouse.mdm.database import MdmEntity, MdmSecurity, MdmSourceRef

        source_id = (
            f"{txn_row.get('accession_number')}:"
            f"{txn_row.get('owner_index')}:"
            f"{txn_row.get('txn_index')}"
        )
        source_match = self.session.scalar(
            select(MdmSourceRef.entity_id)
            .join(MdmEntity, MdmEntity.entity_id == MdmSourceRef.entity_id)
            .where(MdmSourceRef.source_system == "ownership_filing")
            .where(MdmSourceRef.source_id == source_id)
            .where(MdmEntity.entity_type == "security")
        )
        if source_match:
            return source_match
        issuer_entity_id = self._company_entity_id(txn_row.get("issuer_cik"))
        title = txn_row.get("security_title")
        if not title:
            return None
        canonical = " ".join(word.capitalize() for word in str(title).split())
        stmt = select(MdmSecurity.entity_id).where(MdmSecurity.canonical_title == canonical)
        if issuer_entity_id:
            stmt = stmt.where(MdmSecurity.issuer_entity_id == issuer_entity_id)
        return self.session.scalar(stmt)

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

    @staticmethod
    def _json_property(value):
        if hasattr(value, "isoformat"):
            return value.isoformat()
        if hasattr(value, "__float__") and value.__class__.__module__ == "decimal":
            return float(value)
        return value
