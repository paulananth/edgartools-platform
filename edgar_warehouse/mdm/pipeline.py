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
from datetime import date, datetime, timezone
from typing import Iterable, Optional

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from edgar_warehouse.mdm.graph import GraphSyncEngine
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
    # ── Existing (ownership + ADV) ────────────────────────────────────────────
    "IS_INSIDER",
    "HOLDS",
    "COMPANY_HOLDS",
    "ISSUED_BY",
    "IS_ENTITY_OF",
    "HAS_PARENT_COMPANY",
    "MANAGES_FUND",
    "IS_PERSON_OF",
    # ── New (fundamentals research) ───────────────────────────────────────────
    "EMPLOYED_BY",          # Person → Company     (DEF 14A proxy)
    "AUDITED_BY",           # Company → AuditFirm  (10-K dei_AuditorFirmId XBRL)
    "INSTITUTIONAL_HOLDS",  # Adviser → Security   (13F holdings)
)

_RELATIONSHIP_SOURCE_LIMIT_MULTIPLIER = 50
_RELATIONSHIP_SOURCE_LIMIT_MINIMUM = 100


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

    @staticmethod
    def _bounded_relationship_sql(sql: str, remaining: Optional[int], existing: int = 0) -> str:
        """Append a LIMIT that grows with `existing` so the source window keeps
        advancing past already-converted rows on repeat runs.

        Without `existing` in the limit, every run re-reads the same leading
        slice of the (unordered-by-default) source query: rows already turned
        into relationships come back as `skipped_existing` and the run never
        reaches fresh rows further down the table — repeat invocations with the
        same `--limit` plateau at whatever the first run produced. Growing the
        window by `existing` guarantees it always extends past the previously
        converted prefix into unconverted territory, given a stable ORDER BY.
        """
        if remaining is None:
            return sql
        source_limit = int(existing) + max(
            int(remaining) * _RELATIONSHIP_SOURCE_LIMIT_MULTIPLIER,
            _RELATIONSHIP_SOURCE_LIMIT_MINIMUM,
        )
        return f"{sql.rstrip()} LIMIT {source_limit}"

    def _fetch_optional_relationship_rows(
        self,
        sql: str,
        remaining: Optional[int],
        *,
        rel_type_name: str,
        source_table: str,
        existing: int = 0,
    ) -> list[dict]:
        try:
            return self.silver.fetch(self._bounded_relationship_sql(sql, remaining, existing))
        except Exception as exc:
            if not self._is_missing_source_table(exc, source_table):
                raise
            print(json.dumps({
                "event": "mdm_relationship_skip",
                "rel_type": rel_type_name,
                "reason": "missing_source_table",
                "source_table": source_table,
                "ts": datetime.now(timezone.utc).isoformat(),
            }), file=sys.stderr, flush=True)
            return []

    @staticmethod
    def _is_missing_source_table(exc: Exception, table_name: str) -> bool:
        message = str(exc).lower()
        table = table_name.lower()
        missing_markers = ("does not exist", "not found", "catalog error", "binder error")
        return table in message and any(marker in message for marker in missing_markers)

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
                   t.security_title, f.cik AS issuer_cik, FALSE AS is_derivative
            FROM sec_ownership_non_derivative_txn t
            JOIN sec_company_filing f ON t.accession_number = f.accession_number
            WHERE t.security_title IS NOT NULL
            UNION ALL
            SELECT DISTINCT t.accession_number, t.owner_index, t.txn_index,
                   t.security_title, f.cik AS issuer_cik, TRUE AS is_derivative
            FROM sec_ownership_derivative_txn t
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
        sync_engine = GraphSyncEngine.build(self.session)
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
        if rel_type_name == "COMPANY_HOLDS":
            return self._derive_company_holds(sync_engine, remaining)
        if rel_type_name == "ISSUED_BY":
            return self._derive_issued_by(sync_engine, remaining)
        if rel_type_name == "IS_ENTITY_OF":
            return self._derive_is_entity_of(sync_engine, remaining)
        if rel_type_name == "HAS_PARENT_COMPANY":
            return self._derive_has_parent_company(sync_engine, remaining)
        if rel_type_name == "MANAGES_FUND":
            return self._derive_manages_fund(sync_engine, remaining)
        if rel_type_name == "IS_PERSON_OF":
            return self._derive_is_person_of(sync_engine, remaining)
        if rel_type_name == "EMPLOYED_BY":
            return self._derive_employed_by(sync_engine, remaining)
        if rel_type_name == "AUDITED_BY":
            return self._derive_audited_by(sync_engine, remaining)
        if rel_type_name == "INSTITUTIONAL_HOLDS":
            return self._derive_institutional_holds(sync_engine, remaining)
        raise KeyError(f"Unknown relationship type '{rel_type_name}'")

    def _derive_is_insider(self, sync_engine: GraphSyncEngine, remaining: Optional[int]) -> tuple[int, int, int, int, int]:
        sql = """
            SELECT o.accession_number, o.owner_index, o.owner_cik, o.owner_name,
                   o.is_director, o.is_officer, o.is_ten_percent_owner, o.is_other,
                   o.officer_title,
                   f.cik AS issuer_cik, f.report_date AS period_of_report
            FROM sec_ownership_reporting_owner o
            JOIN sec_company_filing f ON o.accession_number = f.accession_number
            ORDER BY o.accession_number, o.owner_index
        """
        company_ciks = self._company_cik_set()
        existing = self._relationship_count("IS_INSIDER")
        inserted = 0
        skipped_corporate = 0
        skipped_unresolved_source = 0
        skipped_unresolved_target = 0
        skipped_existing = 0
        for row in self.silver.fetch(self._bounded_relationship_sql(sql, remaining, existing)):
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
                   FALSE AS is_derivative,
                   NULL AS conversion_or_exercise_price,
                   NULL AS exercise_date,
                   NULL AS expiration_date,
                   NULL AS underlying_security_title,
                   NULL AS underlying_security_shares,
                   o.owner_cik, o.owner_name,
                   f.cik AS issuer_cik
            FROM sec_ownership_non_derivative_txn t
            JOIN sec_ownership_reporting_owner o
              ON t.accession_number = o.accession_number
             AND t.owner_index = o.owner_index
            JOIN sec_company_filing f ON t.accession_number = f.accession_number
            WHERE t.security_title IS NOT NULL
            UNION ALL
            SELECT t.accession_number, t.owner_index, t.txn_index,
                   t.security_title, t.transaction_date, t.shares_owned_after,
                   t.ownership_direct_indirect,
                   TRUE AS is_derivative,
                   t.conversion_or_exercise_price,
                   t.exercise_date,
                   t.expiration_date,
                   t.underlying_security_title,
                   t.underlying_security_shares,
                   o.owner_cik, o.owner_name,
                   f.cik AS issuer_cik
            FROM sec_ownership_derivative_txn t
            JOIN sec_ownership_reporting_owner o
              ON t.accession_number = o.accession_number
             AND t.owner_index = o.owner_index
            JOIN sec_company_filing f ON t.accession_number = f.accession_number
            WHERE t.security_title IS NOT NULL
            ORDER BY accession_number, owner_index, txn_index
        """
        company_ciks = self._company_cik_set()
        existing = self._relationship_count("HOLDS")
        inserted = 0
        skipped_corporate = 0
        skipped_unresolved_source = 0
        skipped_unresolved_target = 0
        skipped_existing = 0
        for row in self.silver.fetch(self._bounded_relationship_sql(sql, remaining, existing)):
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
                "is_derivative": bool(row.get("is_derivative")),
                "conversion_or_exercise_price": self._json_property(row.get("conversion_or_exercise_price")),
                "exercise_date": self._json_property(row.get("exercise_date")),
                "expiration_date": self._json_property(row.get("expiration_date")),
                "underlying_security_title": row.get("underlying_security_title"),
                "underlying_security_shares": self._json_property(row.get("underlying_security_shares")),
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

    def _derive_company_holds(self, sync_engine: GraphSyncEngine, remaining: Optional[int]) -> tuple[int, int, int, int, int]:
        sql = """
            SELECT t.accession_number, t.owner_index, t.txn_index,
                   t.security_title, t.transaction_date, t.shares_owned_after,
                   t.ownership_direct_indirect,
                   FALSE AS is_derivative,
                   NULL AS conversion_or_exercise_price,
                   NULL AS exercise_date,
                   NULL AS expiration_date,
                   NULL AS underlying_security_title,
                   NULL AS underlying_security_shares,
                   o.owner_cik, o.owner_name,
                   f.cik AS issuer_cik
            FROM sec_ownership_non_derivative_txn t
            JOIN sec_ownership_reporting_owner o
              ON t.accession_number = o.accession_number
             AND t.owner_index = o.owner_index
            JOIN sec_company_filing f ON t.accession_number = f.accession_number
            WHERE t.security_title IS NOT NULL
            UNION ALL
            SELECT t.accession_number, t.owner_index, t.txn_index,
                   t.security_title, t.transaction_date, t.shares_owned_after,
                   t.ownership_direct_indirect,
                   TRUE AS is_derivative,
                   t.conversion_or_exercise_price,
                   t.exercise_date,
                   t.expiration_date,
                   t.underlying_security_title,
                   t.underlying_security_shares,
                   o.owner_cik, o.owner_name,
                   f.cik AS issuer_cik
            FROM sec_ownership_derivative_txn t
            JOIN sec_ownership_reporting_owner o
              ON t.accession_number = o.accession_number
             AND t.owner_index = o.owner_index
            JOIN sec_company_filing f ON t.accession_number = f.accession_number
            WHERE t.security_title IS NOT NULL
            ORDER BY accession_number, owner_index, txn_index
        """
        company_ciks = self._company_cik_set()
        existing = self._relationship_count("COMPANY_HOLDS")
        inserted = 0
        skipped_corporate = 0
        skipped_unresolved_source = 0
        skipped_unresolved_target = 0
        skipped_existing = 0
        for row in self.silver.fetch(self._bounded_relationship_sql(sql, remaining, existing)):
            owner_cik = row.get("owner_cik")
            if owner_cik not in company_ciks:
                # skipped_corporate here means non-corporate owner (inverse of
                # IS_INSIDER/HOLDS — COMPANY_HOLDS wants corporate owners only)
                skipped_corporate += 1
                continue
            company_id = self._company_entity_id(owner_cik)
            if company_id is None:
                skipped_unresolved_source += 1
                continue
            security_id = self._security_entity_id(row)
            if security_id is None:
                skipped_unresolved_target += 1
                print(json.dumps({
                    "event": "mdm_relationship_skip",
                    "rel_type": "COMPANY_HOLDS",
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
                "is_derivative": bool(row.get("is_derivative")),
                "conversion_or_exercise_price": self._json_property(row.get("conversion_or_exercise_price")),
                "exercise_date": self._json_property(row.get("exercise_date")),
                "expiration_date": self._json_property(row.get("expiration_date")),
                "underlying_security_title": row.get("underlying_security_title"),
                "underlying_security_shares": self._json_property(row.get("underlying_security_shares")),
            }
            _rel, created = sync_engine.ensure_relationship(
                rel_type_name="COMPANY_HOLDS",
                source_entity_id=company_id,
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

    def _derive_has_parent_company(self, sync_engine: GraphSyncEngine, remaining: Optional[int]) -> tuple[int, int, int, int, int]:
        from edgar_warehouse.mdm.database import MdmCompany

        inserted = 0
        skipped_corporate = 0
        skipped_unresolved_source = 0
        skipped_unresolved_target = 0
        skipped_existing = 0
        for company in self.session.scalars(
            select(MdmCompany)
            .where(MdmCompany.parent_company_entity_id.isnot(None))
            .order_by(MdmCompany.cik)
        ):
            if company.entity_id == company.parent_company_entity_id:
                skipped_unresolved_target += 1
                continue
            _rel, created = sync_engine.ensure_relationship(
                rel_type_name="HAS_PARENT_COMPANY",
                source_entity_id=company.entity_id,
                target_entity_id=company.parent_company_entity_id,
                source_system="derived",
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

    def backfill_security_issuers(self) -> int:
        """Repair mdm_security rows where issuer_entity_id is NULL but the company is now in MDM.

        5-why root cause: run_companies(limit=100) processes at most 100 of 5400 companies per
        run, so when run_securities() creates a security its issuer may not yet exist in
        mdm_company.  On subsequent runs the resolver finds the existing NULL-issuer row and
        returns it unchanged.  This method does one full scan of silver to patch those rows.

        Returns the number of rows updated.
        """
        from edgar_warehouse.mdm.database import MdmCompany, MdmSecurity

        # canonical_title normalisation must match run_securities()
        def _canonical(raw: str) -> str:
            return " ".join(w.capitalize() for w in (raw or "").split())

        sql = """
            SELECT DISTINCT t.security_title, f.cik AS issuer_cik
            FROM   sec_ownership_non_derivative_txn t
            JOIN   sec_company_filing f ON f.accession_number = t.accession_number
            WHERE  t.security_title IS NOT NULL
            UNION
            SELECT DISTINCT t.security_title, f.cik AS issuer_cik
            FROM   sec_ownership_derivative_txn t
            JOIN   sec_company_filing f ON f.accession_number = t.accession_number
            WHERE  t.security_title IS NOT NULL
        """
        rows = self.silver.fetch(sql)

        updated = 0
        for row in rows:
            canonical = _canonical(row.get("security_title") or "")
            issuer_cik = row.get("issuer_cik")
            if not canonical or issuer_cik is None:
                continue

            issuer_entity_id = self._company_entity_id(issuer_cik)
            if not issuer_entity_id:
                continue

            result = self.session.execute(
                update(MdmSecurity)
                .where(MdmSecurity.canonical_title == canonical)
                .where(MdmSecurity.issuer_entity_id.is_(None))
                .values(issuer_entity_id=issuer_entity_id)
            )
            updated += result.rowcount

        if updated:
            self.session.commit()
        return updated

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

        source_id = _ownership_security_source_id(txn_row)
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

    def _adviser_entity_id_by_cik(self, cik) -> Optional[str]:
        """Look up an adviser entity_id by CIK.

        Used for 13F filers, which are identified by CIK in the SEC 13F filer
        list rather than by an ADV accession number.
        """
        if cik is None:
            return None
        from edgar_warehouse.mdm.database import MdmAdviser
        from sqlalchemy import select
        return self.session.scalar(
            select(MdmAdviser.entity_id).where(MdmAdviser.cik == int(cik))
        )

    def _audit_firm_entity_id(
        self, pcaob_id: Optional[str], firm_name: Optional[str]
    ) -> Optional[str]:
        """Look up an audit firm entity_id by PCAOB ID (primary) or firm name (fallback).

        Lookup-only — AUDITED_BY is seeded from the Big 4 + Next 6 roster (AD-09),
        which covers ~99.5% of exchange-listed audits.  Unknown firms are skipped
        and logged; they do not auto-create new mdm_audit_firm rows.
        """
        from edgar_warehouse.mdm.database import MdmAuditFirm
        from sqlalchemy import select
        # Primary: match on PCAOB registration number (authoritative identifier)
        if pcaob_id:
            result = self.session.scalar(
                select(MdmAuditFirm.entity_id).where(MdmAuditFirm.pcaob_firm_id == str(pcaob_id))
            )
            if result:
                return result
        # Fallback: case-insensitive name match
        if firm_name:
            from sqlalchemy import func as sqlfunc
            result = self.session.scalar(
                select(MdmAuditFirm.entity_id).where(
                    sqlfunc.lower(MdmAuditFirm.canonical_name) == firm_name.lower().strip()
                )
            )
            if result:
                return result
        return None

    def _ensure_proxy_person(
        self, exec_name: str, company_cik: int, accession_number: str
    ) -> Optional[str]:
        """Return entity_id for a proxy executive, creating a stub if not found.

        Resolution order (AD-06 hybrid CIK crosswalk + UUID5 fallback):
        1. Exact CIK match via _person_entity_id (Form 4 anchor)
        2. Canonical name match via _person_entity_id
        3. UUID5(NAMESPACE_DNS, f"{company_cik}:{normalized_name}") — deterministic stub

        IMPORTANT: UUID5 deduplication is intentionally per-company (AD-06).
        An exec named "John Smith" at AAPL (cik=320193) and at MSFT (cik=789019)
        will receive two different entity_ids.  MDM merge pass (Splink) may later
        link them, but that is a separate pipeline step outside this derivation.

        Source ref: source_priority=50, confidence=0.5 — lower than Form 4 anchor
        (priority=10) so the Form 4 record wins on survivorship if the person is
        later resolved to a canonical entity.
        """
        import unicodedata
        import uuid as _uuid

        if not exec_name:
            return None

        # Step 1 + 2: Check existing MDM person records (Form 4 anchor path)
        existing = self._person_entity_id(None, exec_name)
        if existing:
            return existing

        # Step 3: Create UUID5 stub — deterministic so re-runs are idempotent
        normalized = unicodedata.normalize("NFKD", exec_name.strip().lower())
        stub_id = str(_uuid.uuid5(_uuid.NAMESPACE_DNS, f"{company_cik}:{normalized}"))

        # Check whether the stub already exists (idempotency guard)
        from edgar_warehouse.mdm.database import MdmEntity, MdmPerson, MdmSourceRef
        from sqlalchemy import select
        already = self.session.scalar(
            select(MdmPerson.entity_id).where(MdmPerson.entity_id == stub_id)
        )
        if already:
            return already

        # Create MdmEntity + MdmPerson + MdmSourceRef
        entity = MdmEntity(
            entity_id=stub_id,
            entity_type="person",
            resolution_method="uuid5_proxy_stub",
            confidence=0.5,
        )
        self.session.add(entity)
        person = MdmPerson(
            entity_id=stub_id,
            canonical_name=exec_name.strip(),
            name_variants=[exec_name.strip()],
        )
        self.session.add(person)
        # Source ref provides audit trail back to the DEF 14A filing
        source_ref = MdmSourceRef(
            entity_id=stub_id,
            source_system="proxy_filing",
            source_id=accession_number,
            source_priority=50,
            confidence=0.5,
        )
        self.session.add(source_ref)
        self.session.flush()
        return stub_id

    def _ensure_security_by_cusip(
        self,
        cusip: str,
        issuer_name: Optional[str],
        security_class: Optional[str],
    ) -> Optional[str]:
        """Return entity_id for a security identified by CUSIP, auto-creating if absent.

        13F holdings reference securities overwhelmingly outside the Form 4-derived
        mdm_security universe, so auto-creation is required (unlike AUDITED_BY which
        is lookup-only).  UUID5(NAMESPACE_DNS, f"cusip:{cusip}") ensures idempotency
        across multiple bootstrap runs.
        """
        import uuid as _uuid

        if not cusip:
            return None

        # Check existing by CUSIP (fastest path — indexed)
        from edgar_warehouse.mdm.database import MdmEntity, MdmSecurity, MdmSourceRef
        from sqlalchemy import select
        existing = self.session.scalar(
            select(MdmSecurity.entity_id).where(MdmSecurity.cusip == cusip)
        )
        if existing:
            # Opportunistically set security_class if still NULL
            if security_class:
                rec = self.session.get(MdmSecurity, existing)
                if rec and rec.security_class is None:
                    rec.security_class = security_class
                    self.session.flush()
            return existing

        # Auto-create new security stub
        stub_id = str(_uuid.uuid5(_uuid.NAMESPACE_DNS, f"cusip:{cusip}"))

        # Idempotency guard — could exist in entity table without security row
        already = self.session.scalar(
            select(MdmSecurity.entity_id).where(MdmSecurity.entity_id == stub_id)
        )
        if already:
            return already

        canonical = issuer_name.strip() if issuer_name else f"CUSIP:{cusip}"
        entity = MdmEntity(
            entity_id=stub_id,
            entity_type="security",
            resolution_method="cusip_stub",
            confidence=0.7,
        )
        self.session.add(entity)
        security = MdmSecurity(
            entity_id=stub_id,
            canonical_title=canonical,
            cusip=cusip,
            security_class=security_class,
        )
        self.session.add(security)
        source_ref = MdmSourceRef(
            entity_id=stub_id,
            source_system="thirteenf_filing",
            source_id=f"cusip:{cusip}",
            source_priority=60,
            confidence=0.7,
        )
        self.session.add(source_ref)
        self.session.flush()
        return stub_id

    # ── New derivation methods ────────────────────────────────────────────────

    def _derive_employed_by(
        self, sync_engine: GraphSyncEngine, remaining: Optional[int]
    ) -> tuple[int, int, int, int, int]:
        """Derive EMPLOYED_BY edges from sec_executive_record (DEF 14A proxy filings).

        Person resolution order (AD-06):
        1. Exact Form 4 anchor via _person_entity_id
        2. UUID5 proxy stub via _ensure_proxy_person (creates if absent)

        Dedup key: (source_entity_id, target_entity_id, fiscal_year).
        One EMPLOYED_BY edge per person-company-year combination.
        """
        sql = """
            SELECT cik, accession_number, fiscal_year, exec_name, exec_role,
                   total_comp, base_salary, bonus, stock_awards,
                   option_awards, non_equity_incentive
            FROM sec_executive_record
            WHERE exec_name IS NOT NULL
            ORDER BY cik, fiscal_year, accession_number, exec_name
        """
        existing = self._relationship_count("EMPLOYED_BY")
        inserted = 0
        skipped_corporate = 0
        skipped_unresolved_source = 0
        skipped_unresolved_target = 0
        skipped_existing = 0

        for row in self._fetch_optional_relationship_rows(
            sql,
            remaining,
            rel_type_name="EMPLOYED_BY",
            source_table="sec_executive_record",
            existing=existing,
        ):
            cik = row.get("cik")
            exec_name = row.get("exec_name") or ""
            accession_number = row.get("accession_number") or ""
            fiscal_year = row.get("fiscal_year")

            company_id = self._company_entity_id(cik)
            if company_id is None:
                skipped_unresolved_target += 1
                print(json.dumps({
                    "event": "mdm_relationship_skip",
                    "rel_type": "EMPLOYED_BY",
                    "reason": "unresolved_target",
                    "cik": cik,
                    "ts": datetime.now(timezone.utc).isoformat(),
                }), file=sys.stderr, flush=True)
                continue

            person_id = self._ensure_proxy_person(exec_name, int(cik), accession_number)
            if person_id is None:
                skipped_unresolved_source += 1
                print(json.dumps({
                    "event": "mdm_relationship_skip",
                    "rel_type": "EMPLOYED_BY",
                    "reason": "unresolved_source",
                    "exec_name": exec_name,
                    "cik": cik,
                    "ts": datetime.now(timezone.utc).isoformat(),
                }), file=sys.stderr, flush=True)
                continue

            effective_from = date(int(fiscal_year), 1, 1) if fiscal_year else None
            _rel, created = sync_engine.ensure_relationship(
                rel_type_name="EMPLOYED_BY",
                source_entity_id=person_id,
                target_entity_id=company_id,
                properties={
                    "role":               row.get("exec_role"),
                    "title":              row.get("exec_role"),
                    "fiscal_year":        fiscal_year,
                    "total_compensation": row.get("total_comp"),
                    "stock_awards":       row.get("stock_awards"),
                    "option_awards":      row.get("option_awards"),
                    "non_equity_incentive": row.get("non_equity_incentive"),
                    "source_accession":   accession_number,
                },
                effective_from=effective_from,
                source_system="proxy_filing",
                source_accession=accession_number,
            )
            if created:
                inserted += 1
            else:
                skipped_existing += 1
                print(json.dumps({
                    "event": "mdm_relationship_skip",
                    "rel_type": "EMPLOYED_BY",
                    "reason": "existing",
                    "source_entity_id": person_id,
                    "target_entity_id": company_id,
                    "ts": datetime.now(timezone.utc).isoformat(),
                }), file=sys.stderr, flush=True)
            if remaining is not None and inserted >= remaining:
                break

        return inserted, skipped_corporate, skipped_unresolved_source, skipped_unresolved_target, skipped_existing

    def _derive_audited_by(
        self, sync_engine: GraphSyncEngine, remaining: Optional[int]
    ) -> tuple[int, int, int, int, int]:
        """Derive AUDITED_BY edges from sec_accounting_flag (10-K XBRL DEI facts).

        Audit firm resolution (AD-08):
        1. PCAOB firm ID — authoritative (dei_AuditorFirmId XBRL concept)
        2. Firm name fuzzy match — fallback for FY2020 filings predating mandatory DEI

        Lookup-only: if neither PCAOB ID nor name resolves to a seeded audit_firm
        entity, the row is skipped.  The Big 4 + Next 6 seed (AD-09) covers ~99.5%
        of exchange-listed audits; long-tail firms are acceptable gaps in v1.

        auditor_changed is computed as TRUE when the firm_name differs from the
        immediately prior fiscal year's row for the same CIK.
        """
        # Fetch all accounting flag rows ordered by cik, fiscal_year so we can
        # detect auditor changes with a simple prev-row comparison.
        sql = """
            SELECT cik, accession_number, fiscal_year, period_end,
                   auditor_pcaob_id, auditor_name, icfr_attestation
            FROM sec_accounting_flag
            WHERE auditor_name IS NOT NULL OR auditor_pcaob_id IS NOT NULL
            ORDER BY cik, fiscal_year
        """
        existing = self._relationship_count("AUDITED_BY")
        inserted = 0
        skipped_corporate = 0
        skipped_unresolved_source = 0
        skipped_unresolved_target = 0
        skipped_existing = 0

        prev_cik: Optional[int] = None
        prev_auditor_name: Optional[str] = None

        for row in self._fetch_optional_relationship_rows(
            sql,
            remaining,
            rel_type_name="AUDITED_BY",
            source_table="sec_accounting_flag",
            existing=existing,
        ):
            cik = row.get("cik")
            pcaob_id = row.get("auditor_pcaob_id")
            auditor_name = row.get("auditor_name")
            fiscal_year = row.get("fiscal_year")
            accession_number = row.get("accession_number") or ""
            icfr_attestation = row.get("icfr_attestation")

            # Detect auditor change vs prior fiscal year (same CIK, ORDER BY cik, fiscal_year)
            if cik == prev_cik and prev_auditor_name is not None and auditor_name:
                auditor_changed = (auditor_name.lower().strip() != prev_auditor_name.lower().strip())
            else:
                auditor_changed = False
            prev_cik = cik
            prev_auditor_name = auditor_name

            company_id = self._company_entity_id(cik)
            if company_id is None:
                skipped_unresolved_source += 1
                print(json.dumps({
                    "event": "mdm_relationship_skip",
                    "rel_type": "AUDITED_BY",
                    "reason": "unresolved_source",
                    "cik": cik,
                    "ts": datetime.now(timezone.utc).isoformat(),
                }), file=sys.stderr, flush=True)
                continue

            audit_firm_id = self._audit_firm_entity_id(pcaob_id, auditor_name)
            if audit_firm_id is None:
                skipped_unresolved_target += 1
                print(json.dumps({
                    "event": "mdm_relationship_skip",
                    "rel_type": "AUDITED_BY",
                    "reason": "unresolved_target",
                    "cik": cik,
                    "auditor_pcaob_id": pcaob_id,
                    "auditor_name": auditor_name,
                    "ts": datetime.now(timezone.utc).isoformat(),
                }), file=sys.stderr, flush=True)
                continue

            effective_from = date(int(fiscal_year), 1, 1) if fiscal_year else None
            _rel, created = sync_engine.ensure_relationship(
                rel_type_name="AUDITED_BY",
                source_entity_id=company_id,
                target_entity_id=audit_firm_id,
                properties={
                    "fiscal_year":      fiscal_year,
                    "pcaob_firm_id":    pcaob_id,
                    "icfr_attestation": icfr_attestation,
                    "auditor_changed":  auditor_changed,
                    "source_accession": accession_number,
                },
                effective_from=effective_from,
                source_system="tenk_filing",
                source_accession=accession_number,
            )
            if created:
                inserted += 1
            else:
                skipped_existing += 1
                print(json.dumps({
                    "event": "mdm_relationship_skip",
                    "rel_type": "AUDITED_BY",
                    "reason": "existing",
                    "source_entity_id": company_id,
                    "target_entity_id": audit_firm_id,
                    "ts": datetime.now(timezone.utc).isoformat(),
                }), file=sys.stderr, flush=True)
            if remaining is not None and inserted >= remaining:
                break

        return inserted, skipped_corporate, skipped_unresolved_source, skipped_unresolved_target, skipped_existing

    def _derive_institutional_holds(
        self, sync_engine: GraphSyncEngine, remaining: Optional[int]
    ) -> tuple[int, int, int, int, int]:
        """Derive INSTITUTIONAL_HOLDS edges from sec_thirteenf_holding (13F-HR filings).

        Source entity: Adviser (filing manager CIK → mdm_adviser.cik)
        Target entity: Security (CUSIP → mdm_security.cusip, auto-created if absent)

        Security auto-creation rationale: 13F holdings overwhelmingly reference
        securities outside the Form 4-derived mdm_security universe.  Auto-creating
        via _ensure_security_by_cusip is necessary to capture institutional coverage.
        The UUID5 key (f"cusip:{cusip}") guarantees idempotency across runs.

        Rows without a CUSIP are skipped — security identity cannot be established.
        Rows whose filing CIK cannot be resolved to an mdm_adviser are skipped;
        the 13F filer list bootstrap must complete before INSTITUTIONAL_HOLDS derivation.
        """
        sql = """
            SELECT cik, accession_number, period_of_report, cusip,
                   issuer_name, security_title, shares_held, market_value,
                   put_call, discretion_type, security_class
            FROM sec_thirteenf_holding
            WHERE cusip IS NOT NULL
            ORDER BY cik, accession_number, cusip
        """
        existing = self._relationship_count("INSTITUTIONAL_HOLDS")
        inserted = 0
        skipped_corporate = 0
        skipped_unresolved_source = 0
        skipped_unresolved_target = 0
        skipped_existing = 0

        for row in self._fetch_optional_relationship_rows(
            sql,
            remaining,
            rel_type_name="INSTITUTIONAL_HOLDS",
            source_table="sec_thirteenf_holding",
            existing=existing,
        ):
            cik = row.get("cik")
            cusip = row.get("cusip") or ""
            accession_number = row.get("accession_number") or ""
            period_of_report = row.get("period_of_report")
            security_class = row.get("security_class")
            issuer_name = row.get("issuer_name")

            if not cusip:
                skipped_unresolved_target += 1
                continue

            adviser_id = self._adviser_entity_id_by_cik(cik)
            if adviser_id is None:
                skipped_unresolved_source += 1
                print(json.dumps({
                    "event": "mdm_relationship_skip",
                    "rel_type": "INSTITUTIONAL_HOLDS",
                    "reason": "unresolved_source",
                    "cik": cik,
                    "ts": datetime.now(timezone.utc).isoformat(),
                }), file=sys.stderr, flush=True)
                continue

            security_id = self._ensure_security_by_cusip(cusip, issuer_name, security_class)
            if security_id is None:
                skipped_unresolved_target += 1
                print(json.dumps({
                    "event": "mdm_relationship_skip",
                    "rel_type": "INSTITUTIONAL_HOLDS",
                    "reason": "unresolved_target",
                    "cusip": cusip,
                    "ts": datetime.now(timezone.utc).isoformat(),
                }), file=sys.stderr, flush=True)
                continue

            _rel, created = sync_engine.ensure_relationship(
                rel_type_name="INSTITUTIONAL_HOLDS",
                source_entity_id=adviser_id,
                target_entity_id=security_id,
                properties={
                    "quarter_end":      str(period_of_report) if period_of_report else None,
                    "shares_held":      row.get("shares_held"),
                    "market_value":     row.get("market_value"),
                    "ownership_pct":    None,   # computed by gold layer (shares / shares_outstanding)
                    "put_call":         row.get("put_call"),
                    "discretion_type":  row.get("discretion_type"),
                    "source_accession": accession_number,
                },
                effective_from=date.fromisoformat(str(period_of_report)) if period_of_report else None,
                source_system="thirteenf_filing",
                source_accession=accession_number,
            )
            if created:
                inserted += 1
            else:
                skipped_existing += 1
                print(json.dumps({
                    "event": "mdm_relationship_skip",
                    "rel_type": "INSTITUTIONAL_HOLDS",
                    "reason": "existing",
                    "source_entity_id": adviser_id,
                    "target_entity_id": security_id,
                    "ts": datetime.now(timezone.utc).isoformat(),
                }), file=sys.stderr, flush=True)
            if remaining is not None and inserted >= remaining:
                break

        return inserted, skipped_corporate, skipped_unresolved_source, skipped_unresolved_target, skipped_existing

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


def _ownership_security_source_id(txn_row: dict) -> str:
    accession = txn_row.get("accession_number")
    owner_index = txn_row.get("owner_index")
    txn_index = txn_row.get("txn_index")
    if txn_row.get("is_derivative"):
        return f"{accession}:derivative:{owner_index}:{txn_index}"
    return f"{accession}:{owner_index}:{txn_index}"
