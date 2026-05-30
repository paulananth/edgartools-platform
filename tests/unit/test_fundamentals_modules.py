"""Regression tests for fundamentals research extension modules.

Covers Branch B silver parsers, derived metrics, market data fallbacks,
audit firm seed integrity, and CLI wiring for the bootstrap-fundamentals
command.

These tests are network-free and run in the fast test tier (``hatch run
test-fast``).
"""

from __future__ import annotations

import datetime
import unittest
from typing import Any


# ---------------------------------------------------------------------------
# 1. text_extractors — regex-based signal extraction from filing prose
# ---------------------------------------------------------------------------

class TextExtractorsTests(unittest.TestCase):
    def test_customer_concentration_simple(self) -> None:
        from edgar_warehouse.parsers.text_extractors import extract_customer_concentration

        text = "One customer accounted for 32% of our net revenue in fiscal year 2023."
        results = extract_customer_concentration(text)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["concept"], "customer_concentration_pct")
        self.assertEqual(results[0]["value"], 32.0)

    def test_customer_concentration_variations(self) -> None:
        from edgar_warehouse.parsers.text_extractors import extract_customer_concentration

        cases = [
            ("Our largest customer represented approximately 28 percent of total revenues.", 28.0),
            ("No customer accounted for more than 10% of net sales.", 10.0),
            ("Customer A comprised 15.3% of revenue.", 15.3),
        ]
        for text, expected_value in cases:
            with self.subTest(text=text):
                results = extract_customer_concentration(text)
                self.assertGreaterEqual(len(results), 1, f"no match for: {text}")
                self.assertEqual(results[0]["value"], expected_value)

    def test_user_metrics_dau_mau(self) -> None:
        from edgar_warehouse.parsers.text_extractors import extract_user_metrics

        text = "Daily active users reached 2.5 billion in Q4. Monthly active users were 3.1 billion."
        results = extract_user_metrics(text)
        concepts = {r["concept"] for r in results}
        self.assertIn("daily_active_users", concepts)
        self.assertIn("monthly_active_users", concepts)

    def test_user_metrics_scaling(self) -> None:
        from edgar_warehouse.parsers.text_extractors import extract_user_metrics

        text = "Paid subscribers totaled 250 million."
        results = extract_user_metrics(text)
        paid = next((r for r in results if r["concept"] == "paid_subscribers"), None)
        self.assertIsNotNone(paid)
        self.assertEqual(paid["value"], 250_000_000)

    def test_headcount_prefers_largest(self) -> None:
        from edgar_warehouse.parsers.text_extractors import extract_headcount

        text = (
            "We had approximately 45,500 full-time employees. "
            "Our engineering team employed 2,300 people."
        )
        result = extract_headcount(text)
        self.assertIsNotNone(result)
        self.assertEqual(result["value"], 45500)

    def test_headcount_returns_none_when_absent(self) -> None:
        from edgar_warehouse.parsers.text_extractors import extract_headcount
        self.assertIsNone(extract_headcount("We had a great year."))

    def test_extract_text_signals_dispatch(self) -> None:
        from edgar_warehouse.parsers.text_extractors import extract_text_signals

        text = (
            "We employed 12,000 people. Largest customer accounted for 18% of revenue. "
            "Monthly active users averaged 800 million."
        )
        signals = extract_text_signals(text)
        self.assertGreaterEqual(len(signals), 3)


# ---------------------------------------------------------------------------
# 2. financials_derived — XBRL fact aggregation + single-period forensic scores
# ---------------------------------------------------------------------------

class FinancialsDerivedTests(unittest.TestCase):
    def _basic_fact_rows(self) -> list[dict[str, Any]]:
        return [
            {"concept": "Revenues", "value": 100_000_000_000},
            {"concept": "NetIncomeLoss", "value": 15_000_000_000},
            {"concept": "Assets", "value": 200_000_000_000},
            {"concept": "Liabilities", "value": 50_000_000_000},
            {"concept": "OperatingIncomeLoss", "value": 25_000_000_000},
            {"concept": "StockholdersEquity", "value": 150_000_000_000},
        ]

    def test_empty_fact_rows_returns_empty(self) -> None:
        from edgar_warehouse.parsers.financials_derived import compute_derived_for_accession
        out = compute_derived_for_accession(
            cik=1, accession_number="x", fiscal_year=2023,
            fiscal_period="FY", period_end="2023-12-31", form_type="10-K", fact_rows=[],
        )
        self.assertEqual(out["sec_financial_derived"], [])

    def test_basic_derivation_produces_row(self) -> None:
        from edgar_warehouse.parsers.financials_derived import compute_derived_for_accession
        out = compute_derived_for_accession(
            cik=320193, accession_number="0001-test", fiscal_year=2023,
            fiscal_period="FY", period_end="2023-12-31", form_type="10-K",
            fact_rows=self._basic_fact_rows(),
        )
        rows = out["sec_financial_derived"]
        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual(row["cik"], 320193)
        self.assertEqual(row["accession_number"], "0001-test")
        self.assertEqual(row["fiscal_year"], 2023)
        # Revenue + EBIT are present in fact rows; derived row must include them
        self.assertEqual(row["revenue"], 100_000_000_000)
        self.assertEqual(row["ebit"], 25_000_000_000)
        # Forensic scores live exclusively on sec_accounting_flag (see audit
        # findings in commit history); derived rows must NOT carry them.
        self.assertNotIn("beneish_m_score", row)
        self.assertNotIn("altman_z_score", row)
        self.assertNotIn("piotroski_f_score", row)

    def test_cross_period_beneish_returns_float_or_none(self) -> None:
        from edgar_warehouse.parsers.accounting_flags import _beneish_cross_period

        curr = {
            "revenue": 100_000, "cost_of_revenue": 40_000, "net_income": 15_000,
            "cash_flow_operating": 18_000, "total_assets": 200_000, "total_debt": 50_000,
            "accounts_receivable": 12_000, "shares_outstanding": 1_000,
            "selling_general_admin_expense": 20_000, "depreciation_amortization": 5_000,
        }
        prev = {
            "revenue": 80_000, "cost_of_revenue": 35_000, "net_income": 10_000,
            "cash_flow_operating": 12_000, "total_assets": 180_000, "total_debt": 60_000,
            "accounts_receivable": 8_000, "shares_outstanding": 1_000,
            "selling_general_admin_expense": 18_000, "depreciation_amortization": 4_500,
        }
        result = _beneish_cross_period(curr, prev)
        self.assertTrue(result is None or isinstance(result, float))

    def test_cross_period_piotroski_in_valid_range(self) -> None:
        from edgar_warehouse.parsers.accounting_flags import _piotroski_full

        curr = {
            "revenue": 100_000, "cost_of_revenue": 40_000, "net_income": 15_000,
            "cash_flow_operating": 18_000, "total_assets": 200_000, "total_debt": 50_000,
        }
        prev = {
            "revenue": 80_000, "cost_of_revenue": 35_000, "net_income": 10_000,
            "cash_flow_operating": 12_000, "total_assets": 180_000, "total_debt": 60_000,
        }
        result = _piotroski_full(curr, prev)
        self.assertTrue(result is None or 0 <= result <= 9)


# ---------------------------------------------------------------------------
# 3. market.wacc — pure-Python WACC computation with optional PriceProvider
# ---------------------------------------------------------------------------

class WaccTests(unittest.TestCase):
    def _apple_inputs(self) -> "WaccInputs":  # noqa: F821
        from edgar_warehouse.market.wacc import WaccInputs
        return WaccInputs(
            ticker="AAPL", period_end="2023-09-30", sic_code="3571",
            total_debt=110_000_000_000,
            interest_expense=3_900_000_000,
            income_tax_expense=16_741_000_000,
            pretax_income=113_736_000_000,
            market_cap_override=2_700_000_000_000,
            beta_override=1.3,
            risk_free_rate_override=0.0425,
            erp_override=0.055,
        )

    def test_compute_wacc_with_overrides(self) -> None:
        from edgar_warehouse.market.wacc import compute_wacc
        result = compute_wacc(self._apple_inputs(), price_provider=None)
        self.assertIsNotNone(result.wacc)
        self.assertGreater(result.wacc, 0.05)
        self.assertLess(result.wacc, 0.20)

    def test_compute_wacc_zero_market_cap_returns_none(self) -> None:
        from edgar_warehouse.market.wacc import compute_wacc, WaccInputs
        inputs = WaccInputs(ticker="X", period_end="2023-01-01", market_cap_override=0)
        result = compute_wacc(inputs, price_provider=None)
        self.assertIsNone(result.wacc)
        self.assertTrue(result.warnings)

    def test_compute_wacc_zero_debt_uses_equity_only(self) -> None:
        from edgar_warehouse.market.wacc import compute_wacc, WaccInputs
        inputs = WaccInputs(
            ticker="X", period_end="2023-01-01",
            market_cap_override=1_000_000_000, total_debt=0,
            beta_override=1.0, risk_free_rate_override=0.04, erp_override=0.055,
        )
        result = compute_wacc(inputs, price_provider=None)
        # 100% equity weight × 9.5% Ke = 9.5%
        self.assertAlmostEqual(result.wacc, 0.095, places=3)
        self.assertEqual(result.debt_weight, 0.0)


# ---------------------------------------------------------------------------
# 4. market.price_provider — no-network fallbacks
# ---------------------------------------------------------------------------

class PriceProviderTests(unittest.TestCase):
    def test_to_date_str_accepts_str_and_date(self) -> None:
        from edgar_warehouse.market.price_provider import _to_date_str
        self.assertEqual(_to_date_str("2023-12-31"), "2023-12-31")
        self.assertEqual(_to_date_str(datetime.date(2023, 12, 31)), "2023-12-31")

    def test_default_erp_fallback(self) -> None:
        from edgar_warehouse.market.price_provider import PriceProvider
        pp = PriceProvider()
        # SIC 9999 won't be in Damodaran map; falls back to default
        erp = pp.get_equity_risk_premium(sic_code="9999")
        self.assertGreater(erp, 0)
        self.assertLess(erp, 0.20)


# ---------------------------------------------------------------------------
# 5. mdm.seed.audit_firms — Big 4 + Next 6 PCAOB seed integrity
# ---------------------------------------------------------------------------

class AuditFirmSeedTests(unittest.TestCase):
    def test_seed_has_ten_firms(self) -> None:
        from edgar_warehouse.mdm.seed.audit_firms import PCAOB_SEED
        self.assertEqual(len(PCAOB_SEED), 10)

    def test_seed_has_four_big_four(self) -> None:
        from edgar_warehouse.mdm.seed.audit_firms import PCAOB_SEED
        big4 = [f for f in PCAOB_SEED if f["big4"]]
        self.assertEqual(len(big4), 4)
        names = {f["firm_name"] for f in big4}
        self.assertEqual(names, {
            "PricewaterhouseCoopers LLP", "Deloitte & Touche LLP",
            "Ernst & Young LLP", "KPMG LLP",
        })

    def test_pcaob_ids_unique(self) -> None:
        from edgar_warehouse.mdm.seed.audit_firms import PCAOB_SEED
        ids = [f["pcaob_firm_id"] for f in PCAOB_SEED]
        self.assertEqual(len(ids), len(set(ids)))

    def test_canonical_names_lowercased(self) -> None:
        from edgar_warehouse.mdm.seed.audit_firms import PCAOB_SEED
        for firm in PCAOB_SEED:
            self.assertEqual(firm["canonical_name"], firm["canonical_name"].lower())

    def test_all_firms_have_required_fields(self) -> None:
        from edgar_warehouse.mdm.seed.audit_firms import PCAOB_SEED
        for firm in PCAOB_SEED:
            self.assertIn("firm_name", firm)
            self.assertIn("pcaob_firm_id", firm)
            self.assertIn("big4", firm)
            self.assertIn("canonical_name", firm)


# ---------------------------------------------------------------------------
# 6. earnings_release parser — backed by edgartools EarningsRelease
# ---------------------------------------------------------------------------

class EarningsReleaseParserTests(unittest.TestCase):
    """edgartools' EarningsRelease requires a structured income-statement
    table to classify a document as an earnings release.  Plain-text HTML
    (no <table>) correctly returns no rows — that is the contract of the
    new v2 parser.
    """

    def test_empty_content_returns_empty(self) -> None:
        from edgar_warehouse.parsers.earnings_release import parse_earnings_release
        out = parse_earnings_release(
            accession_number="0001-x",
            content="",
            form_type="8-K", cik=1, filing_date="2023-12-31",
        )
        self.assertEqual(out["sec_earnings_release"], [])

    def test_non_earnings_8k_returns_empty(self) -> None:
        """Routine non-earnings 8-K (e.g. director resignation) has no
        income statement table → parser returns empty."""
        from edgar_warehouse.parsers.earnings_release import parse_earnings_release
        out = parse_earnings_release(
            accession_number="0001-x",
            content="<html><body>Director resignation.</body></html>",
            form_type="8-K", cik=1, filing_date="2023-12-31",
        )
        self.assertEqual(out["sec_earnings_release"], [])

    def test_text_only_earnings_returns_empty(self) -> None:
        """Even prose mentioning Item 2.02 + revenue figures returns empty
        without a structured income-statement <table>.  This is the
        edgartools contract: structured tables, not text scraping."""
        from edgar_warehouse.parsers.earnings_release import parse_earnings_release
        out = parse_earnings_release(
            accession_number="0001-x",
            content=(
                "<html>Item 2.02 Results of Operations. "
                "Q4 2023 net revenue was $89.5 billion. "
                "Diluted EPS was $2.18.</html>"
            ),
            form_type="8-K", cik=320193, filing_date="2023-11-02",
        )
        self.assertEqual(out["sec_earnings_release"], [])

    def test_bronze_attachment_stub_has_minimal_fields(self) -> None:
        """The _BronzeAttachment stub must carry only the two fields the
        edgartools document path reads."""
        from edgar_warehouse.parsers.earnings_release import _BronzeAttachment
        stub = _BronzeAttachment(content="<html/>")
        self.assertEqual(stub.content, "<html/>")
        self.assertEqual(stub.document, "earnings-release.htm")


# ---------------------------------------------------------------------------
# 7. CLI / orchestrator wiring
# ---------------------------------------------------------------------------

class BootstrapFundamentalsWiringTests(unittest.TestCase):
    def test_command_registered(self) -> None:
        from edgar_warehouse.application.commands import COMMAND_REGISTRY
        self.assertIn("bootstrap-fundamentals", COMMAND_REGISTRY)

    def test_planned_manifest_paths_resolvable(self) -> None:
        from edgar_warehouse.infrastructure.dataset_path_catalog import default_path_resolver
        paths = default_path_resolver().planned_manifest_paths(
            command_name="bootstrap-fundamentals",
            command_path="bootstrap-fundamentals",
            run_id="test-run", scope={},
        )
        # bootstrap-fundamentals is in _DEFAULT_MANIFEST_COMMANDS — emits all 5 layers
        self.assertIn("bronze", paths)
        self.assertIn("silver", paths)
        self.assertIn("gold", paths)
        self.assertIn("staging", paths)
        self.assertIn("artifacts", paths)

    def test_resolve_scope_returns_cik_list_and_mode(self) -> None:
        from datetime import datetime, UTC
        from edgar_warehouse.application.warehouse_orchestrator import _resolve_scope
        scope = _resolve_scope(
            "bootstrap-fundamentals",
            {"cik_list": [1, 2, 3], "mode": "entity-facts"},
            datetime.now(UTC),
        )
        self.assertEqual(scope["cik_list"], [1, 2, 3])
        self.assertEqual(scope["mode"], "entity-facts")

    def test_resolve_scope_defaults_mode_to_per_filing(self) -> None:
        from datetime import datetime, UTC
        from edgar_warehouse.application.warehouse_orchestrator import _resolve_scope
        scope = _resolve_scope("bootstrap-fundamentals", {"cik_list": [1]}, datetime.now(UTC))
        self.assertEqual(scope["mode"], "per-filing")

    def test_cli_subparser_parses_comma_separated_cik_list(self) -> None:
        from edgar_warehouse.cli import build_parser
        parser = build_parser()
        args = parser.parse_args([
            "bootstrap-fundamentals", "--cik-list", "1,2,3",
            "--mode", "entity-facts",
        ])
        self.assertEqual(args.command, "bootstrap-fundamentals")
        self.assertEqual(args.cik_list, [1, 2, 3])
        self.assertEqual(args.mode, "entity-facts")

    def test_bootstrap_fundamentals_not_in_gold_affecting_commands(self) -> None:
        """Plan invariant (AD-13): bootstrap-fundamentals does NOT trigger gold builds.

        Gold is built once by gold-refresh after all Branch A + B silver completes.
        """
        from edgar_warehouse.application.warehouse_orchestrator import GOLD_AFFECTING_COMMANDS
        self.assertNotIn("bootstrap-fundamentals", GOLD_AFFECTING_COMMANDS)


# ---------------------------------------------------------------------------
# 8. MDM graph registry — Snowflake-side wiring for new relationships
# ---------------------------------------------------------------------------

class SnowflakeGraphRegistryTests(unittest.TestCase):
    def test_new_relationship_types_allowed(self) -> None:
        from edgar_warehouse.mdm.snowflake_graph import ALLOWED_RELATIONSHIP_TYPES
        for name in ("AUDITED_BY", "EMPLOYED_BY", "INSTITUTIONAL_HOLDS"):
            self.assertIn(name, ALLOWED_RELATIONSHIP_TYPES)

    def test_new_edge_tables_registered(self) -> None:
        from edgar_warehouse.mdm.snowflake_graph import EDGE_TABLES
        for name in (
            "GRAPH_EDGE_AUDITED_BY",
            "GRAPH_EDGE_EMPLOYED_BY",
            "GRAPH_EDGE_INSTITUTIONAL_HOLDS",
        ):
            self.assertIn(name, EDGE_TABLES)

    def test_new_node_table_registered(self) -> None:
        from edgar_warehouse.mdm.snowflake_graph import NODE_TABLES
        self.assertIn("GRAPH_NODE_AUDITFIRM", NODE_TABLES)


# ---------------------------------------------------------------------------
# 9. MDM pipeline derivation registry
# ---------------------------------------------------------------------------

class FundamentalsGoldBuilderTests(unittest.TestCase):
    """PR-1 Q5-C invariant — PK columns marked nullable=False in PyArrow schemas.

    Snowflake MERGE on a NULL key silently inserts duplicate rows; the only way
    to prevent that at load time is for the Parquet metadata to declare PK
    columns as non-nullable so Snowflake COPY INTO rejects nulls.
    """

    PASSTHROUGH_PK_COLUMNS = {
        "_SEC_FINANCIAL_FACT_SCHEMA":     {"cik", "accession_number", "concept", "fiscal_period", "segment"},
        "_SEC_THIRTEENF_HOLDING_SCHEMA":  {"cik", "accession_number", "holding_index"},
        "_SEC_FINANCIAL_DERIVED_SCHEMA":  {"cik", "accession_number", "fiscal_period"},
    }

    DIMENSIONAL_PK_COLUMNS = {
        "_FACT_EARNINGS_RELEASE_SCHEMA":   {"fact_key"},
        "_FACT_EXECUTIVE_RECORD_SCHEMA":   {"fact_key"},
        "_FACT_ACCOUNTING_FLAG_SCHEMA":    {"fact_key"},
    }

    def test_passthrough_schemas_mark_pk_columns_not_nullable(self) -> None:
        from edgar_warehouse.serving import gold_models
        for schema_name, pk_cols in self.PASSTHROUGH_PK_COLUMNS.items():
            schema = getattr(gold_models, schema_name)
            with self.subTest(schema=schema_name):
                for field in schema:
                    if field.name in pk_cols:
                        self.assertFalse(
                            field.nullable,
                            f"{schema_name}.{field.name} is a PK column and must be nullable=False (Q5-C)",
                        )

    def test_dimensional_schemas_mark_fact_key_not_nullable(self) -> None:
        from edgar_warehouse.serving import gold_models
        for schema_name, pk_cols in self.DIMENSIONAL_PK_COLUMNS.items():
            schema = getattr(gold_models, schema_name)
            with self.subTest(schema=schema_name):
                for field in schema:
                    if field.name in pk_cols:
                        self.assertFalse(
                            field.nullable,
                            f"{schema_name}.{field.name} is the surrogate PK and must be nullable=False (Q5-C)",
                        )

    def test_fundamentals_export_tables_registered(self) -> None:
        """All 6 Branch B tables must be in SNOWFLAKE_EXPORT_TABLES so they
        are written to the snowflake-export bucket during gold-refresh."""
        from edgar_warehouse.infrastructure.run_manifest_builder import SNOWFLAKE_EXPORT_TABLES
        for snow_table in (
            "SEC_FINANCIAL_FACT",
            "SEC_THIRTEENF_HOLDING",
            "SEC_FINANCIAL_DERIVED",
            "EARNINGS_RELEASE",
            "EXECUTIVE_RECORD",
            "ACCOUNTING_FLAG",
        ):
            with self.subTest(table=snow_table):
                self.assertIn(snow_table, SNOWFLAKE_EXPORT_TABLES)

    def test_build_gold_registers_fundamentals_builders(self) -> None:
        """build_gold() return dict must include the 6 new builders so the
        gold-refresh loop emits PyArrow tables for them."""
        from edgar_warehouse.serving import gold_models
        # We need the source code, not a runtime call (gold-refresh requires
        # a live silver connection). Check the function body for the registrations.
        import inspect
        source = inspect.getsource(gold_models.build_gold)
        for builder_key in (
            "sec_financial_fact",
            "sec_thirteenf_holding",
            "sec_financial_derived",
            "fact_earnings_release",
            "fact_executive_record",
            "fact_accounting_flag",
        ):
            with self.subTest(builder=builder_key):
                self.assertIn(f'"{builder_key}"', source,
                              f"build_gold() must register {builder_key}")


class MdmPipelineRegistrationTests(unittest.TestCase):
    def test_new_relationship_types_in_registry(self) -> None:
        from edgar_warehouse.mdm.pipeline import RELATIONSHIP_TYPES
        for name in ("EMPLOYED_BY", "AUDITED_BY", "INSTITUTIONAL_HOLDS"):
            self.assertIn(name, RELATIONSHIP_TYPES)

    def test_new_derive_methods_exist(self) -> None:
        from edgar_warehouse.mdm.pipeline import MDMPipeline
        for method in (
            "_derive_employed_by",
            "_derive_audited_by",
            "_derive_institutional_holds",
            "_audit_firm_entity_id",
            "_adviser_entity_id_by_cik",
            "_ensure_proxy_person",
            "_ensure_security_by_cusip",
        ):
            self.assertTrue(hasattr(MDMPipeline, method), f"MDMPipeline missing {method}")


if __name__ == "__main__":
    unittest.main()
