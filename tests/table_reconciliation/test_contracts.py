from __future__ import annotations

from edgar_warehouse.application.commands.validate_data_quality import _FK_CHECKS
from edgar_warehouse.silver_protection import PROTECTED_TABLE_REGISTRY
from edgar_warehouse.table_reconciliation.contracts import TABLE_CONTRACTS, ParentLink


def test_table_contracts_cover_every_protected_table_except_pipeline_run_lease():
    expected = set(PROTECTED_TABLE_REGISTRY) - {"pipeline_run_lease"}
    assert set(TABLE_CONTRACTS) == expected


def test_pipeline_run_lease_excluded_as_bookkeeping_not_content():
    assert "pipeline_run_lease" not in TABLE_CONTRACTS


def test_every_contract_business_keys_match_protected_table_registry():
    for table_name, contract in TABLE_CONTRACTS.items():
        policy = PROTECTED_TABLE_REGISTRY[table_name]
        assert contract.business_keys == policy.business_keys


def test_root_tables_have_no_bronze_anchor_or_logical_parent():
    root_tables = {
        "sec_company",
        "sec_current_filing_feed",
        "sec_adv_filing",
        "sec_adv_firm_roster",
        "sec_pcaob_firm_identity",
        "sec_raw_object",
    }
    for table_name in root_tables:
        contract = TABLE_CONTRACTS[table_name]
        assert contract.bronze_anchor is None, table_name
        assert contract.logical_parent is None, table_name


def test_thirteenf_holding_is_present_and_scoped_correctly():
    contract = TABLE_CONTRACTS["sec_thirteenf_holding"]
    assert contract.cardinality == "optional_or_many"
    assert contract.logical_parent is not None
    assert contract.logical_parent.parent_table == "sec_thirteenf_filing"
    assert contract.bronze_anchor is not None
    assert contract.bronze_anchor.parent_table == "sec_company_filing"


def test_authority_column_excluded_from_semantic_digest_when_declared():
    company = TABLE_CONTRACTS["sec_company"]
    assert company.authority_column == "last_synced_at"
    assert "last_synced_at" in company.semantic_exclude_columns
    assert "mdm_entity_id" in company.semantic_exclude_columns


def test_sync_bookkeeping_columns_excluded_from_every_tables_semantic_digest():
    """Ticket 11 (2026-09-06): first_sync_run_id/last_sync_run_id are never
    carried by the Snowflake landing export -- PROTECTED_TABLE_REGISTRY's
    provenance_columns alone doesn't cover them (that registry answers a
    different question), so every table's semantic_exclude_columns must
    include both regardless of whether the registry's own provenance_columns
    happens to. Live evidence: 11 of 30 tables failed reconciliation on a
    pure content-hash mismatch with identical key sets on both sides before
    this fix."""
    for table_name, contract in TABLE_CONTRACTS.items():
        assert "first_sync_run_id" in contract.semantic_exclude_columns, table_name
        assert "last_sync_run_id" in contract.semantic_exclude_columns, table_name


def test_denormalized_cik_excluded_for_the_three_ownership_join_tables():
    """Ticket 11 (2026-09-06): 3 of the 6 ownership tables' dbt models
    deliberately join a Snowflake-only `cik` column in from
    sec_company_filing (Ticket 06) -- DuckDB's own tables never had it."""
    for table_name in (
        "sec_ownership_non_derivative_txn",
        "sec_ownership_derivative_txn",
        "sec_ownership_reporting_owner",
    ):
        assert "cik" in TABLE_CONTRACTS[table_name].semantic_exclude_columns, table_name


def test_denormalized_cik_fix_does_not_widen_beyond_the_three_ownership_tables():
    """The fix itself only ever adds `cik` for the three tables above --
    any other table's `cik` membership (e.g. sec_raw_object, which already
    declares `cik` in PROTECTED_TABLE_REGISTRY.provenance_columns for an
    unrelated reason) must come from the registry, not from this fix,
    proving the fix doesn't over-widen to hide a real future `cik`
    discrepancy elsewhere."""
    from edgar_warehouse.silver_protection import PROTECTED_TABLE_REGISTRY
    from edgar_warehouse.table_reconciliation.contracts import (
        _CROSS_SYSTEM_DENORMALIZED_CIK_TABLES,
    )

    for table_name, contract in TABLE_CONTRACTS.items():
        if table_name in _CROSS_SYSTEM_DENORMALIZED_CIK_TABLES:
            continue
        policy = PROTECTED_TABLE_REGISTRY[table_name]
        if "cik" in contract.semantic_exclude_columns:
            assert "cik" in policy.provenance_columns, (
                f"{table_name} excludes cik but isn't in the registry's own "
                "provenance_columns -- the fix widened beyond its intended scope"
            )


def test_no_table_declares_itself_as_its_own_parent():
    for table_name, contract in TABLE_CONTRACTS.items():
        if contract.bronze_anchor is not None:
            assert contract.bronze_anchor.parent_table != table_name
        if contract.logical_parent is not None:
            assert contract.logical_parent.parent_table != table_name


def test_bronze_anchor_agrees_with_validate_data_quality_fk_checks():
    """Regression test for the manual cross-check documented in this module's
    own docstring: every table validate_data_quality.py's _FK_CHECKS already
    covers must resolve to the identical bronze_anchor ParentLink here, so a
    future edit to either list can't silently drift apart (the "sibling path
    silently diverged" failure shape CLAUDE.md documents repeatedly for this
    repo -- ShardedSilverReader._TABLES, the silver-loader OPERATE+SELECT
    gap, the shard-publish/relationship-derivation divergences).
    """
    for child_table, child_column, parent_table, parent_column in _FK_CHECKS:
        contract = TABLE_CONTRACTS[child_table]
        assert contract.bronze_anchor == ParentLink(
            child_table, child_column, parent_table, parent_column
        ), child_table
