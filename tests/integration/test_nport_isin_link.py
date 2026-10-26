"""Real PG16: an ISIN-only N-PORT Security links to its issuer (ticket 102).

The real chain on invented holdings with no usable CUSIP: the holdings and
issuer source extracts (each ISIN from the `isin` pair set), reduce.yaml,
issuer-reduce.yaml, combine.yaml, mdm.prepare dated by `period`, the ISIN
Dataset Contract, then the Merge Stage: an ISIN whose holdings state one
issuer LEI gets ISSUED_BY, starting at the quarter; an ISIN with two LEIs or
none gets no link. Invented values only.
"""

from __future__ import annotations

import io
import json
import zipfile
from pathlib import Path

from sqlalchemy import text

from edgar_warehouse.bookkeeping.clean.artifacts import Artifacts
from edgar_warehouse.mdm.clean.evidence import subject_key
from edgar_warehouse.mdm.clean.merge import MergeStage
from edgar_warehouse.mdm.clean.store import Store, register_policy
from edgar_warehouse.rules import files
from tests.integration import test_clean_mdm_postgres as core
from tests.integration import test_nport_link_start as cusip
from tests.support.rules_authority import register_dataset


CODE = "sec.nport.security.v2"  # ISIN-only Securities share it (ticket 120)
LEI, OTHER = cusip.LEI, "9999000000EXAMPLE024"  # invented; OTHER is LEI-shaped only
ONE, TWO, NONE = "ZZ0000000016", "ZZ0000000024", "ZZ0000000032"  # invented, check digits valid
HOLDINGS = [["A-1", "4", "Example Corp", LEI, "Note"], ["A-2", "5", "Example Corp", LEI, "Note"],
            ["A-1", "6", "Example Corp", LEI, "Bond"], ["A-1", "7", "Example Corp", OTHER, "Bond"],
            ["A-1", "8", "Other Inc", "", "Bond"]]
# A holding with a usable CUSIP stays out of the ISIN's issuers: were it read
# there, ONE would hold two LEIs and lose its link. It is its CUSIP's Security.
CUSIP = "ZZ0000013"
WITH_CUSIP = ["A-1", "9", "Example Corp", OTHER, "Note", CUSIP]
PAIRS = [["4", ONE], ["5", ONE], ["6", TWO], ["7", TWO], ["8", NONE], ["9", ONE]]


def policy_body() -> dict:
    """The CUSIP check's policy; the ISIN-only Security rule is on in the live policy (ticket 79)."""
    return cusip.policy_body()


def prepared_records(root: Path, umbrella: tuple[list[str], ...] = (),
                     with_cusip: list[str] = WITH_CUSIP) -> list[dict]:
    store = Artifacts()
    root.mkdir(parents=True, exist_ok=True)
    body = io.BytesIO()
    with zipfile.ZipFile(body, "w") as z:
        z.writestr("FUND_REPORTED_HOLDING.tsv", "\n".join("\t".join(r) for r in [
            cusip.COLUMNS, *([*h, ""] for h in HOLDINGS), with_cusip]) + "\n")
        z.writestr("SUBMISSION.tsv", "ACCESSION_NUMBER\tFILING_DATE\n"
                   + "".join(f"{a}\t{d}\n" for a, d in cusip.FILINGS.items()))
    raw = store.put_bytes((root / "capture.zip").as_uri(), body.getvalue())
    holdings = cusip.read(store, root / "holdings", "source.yaml", raw, cusip.Q2, lookups={"isin": PAIRS})
    issuers = cusip.issuers(store, root, raw, PAIRS, cusip.Q2, umbrella)
    return cusip.security_records(store, root, holdings, issuers, batch_id="check-isin")


def test_an_isin_only_security_links_to_its_one_issuer(database, tmp_path):
    records = prepared_records(tmp_path)
    links = {r["provenance"]["record_key"]: [l for l in r.get("relationships") or [] if l["type"] == "ISSUED_BY"] for r in records}
    # The CUSIP's own Security comes from the same run (ticket 120), linked to its one LEI.
    assert {k: len(v) for k, v in links.items()} == {ONE: 1, TWO: 0, NONE: 0, CUSIP: 1}
    for code in (cusip.ADV, cusip.GLEIF):
        core.register_reading(database, code, core.contract_body())
    with database.admin.begin() as conn:
        register_dataset(conn, CODE, database.registry, files.mdm_contract(cusip.NAME, CODE))
        policy = register_policy(conn, policy_body())
    stage = MergeStage(Store(database.application))
    cusip.apply(stage, policy, "custodian", [core.source(
        key="custodian", source_code=cusip.ADV, fields={"name": "Example Corp"}, identifiers={"lei": LEI})], 1)
    cusip.apply(stage, policy, "gleif", [core.source(
        key=LEI, source_code=cusip.GLEIF, fields={"name": "Example Corp"}, identifiers={"lei": LEI},
        provenance={"matching": {"nport_issuer": True}})], 2)
    cusip.apply(stage, policy, "q2", records, 3)
    with database.application.connect() as conn:
        periods = [json.loads(p) if isinstance(p, str) else p for (p,) in conn.execute(text(
            "SELECT body->'periods' FROM mdm.current_record WHERE object_type='relationship' "
            "AND body->>'type'='ISSUED_BY'")).all()]
    (only,) = periods
    # ONE's holdings were filed 5 June and 28 May: the link starts at the earlier (ticket 113).
    assert [(p["valid_from"], p["valid_from_basis"]) for p in only] == [(cusip.MAY28, "stated")]


def test_an_isin_counts_a_fund_series_as_its_umbrella_trust(tmp_path):
    """Ticket 23 on the ISIN table: TWO's holdings name two LEIs; with the
    second a sub-fund of the first, TWO has one issuer, the umbrella."""
    records = prepared_records(tmp_path, umbrella=([OTHER, LEI],))
    targets = {r["provenance"]["record_key"]: [l["target_subject"] for l in r.get("relationships") or []
                                               if l["type"] == "ISSUED_BY"] for r in records}
    assert targets == {ONE: [subject_key(cusip.GLEIF, LEI)], TWO: [subject_key(cusip.GLEIF, LEI)], NONE: [],
                       CUSIP: [subject_key(cusip.GLEIF, LEI)]}  # its issuer, a sub-fund, counts as the umbrella


def test_a_cusips_record_carries_every_isin_filed_with_it_and_an_isin_only_one_keeps_its_own(tmp_path):
    """Ticket 138 (no pairing by FIGI in the rules): holding 9 files the CUSIP with ONE, so
    the CUSIP's record carries ONE; ONE's ISIN-only holdings keep their own record, and
    the two meet in MDM by the ISIN."""
    records = {r["provenance"]["record_key"]: r for r in prepared_records(tmp_path)}
    assert set(records) == {ONE, TWO, NONE, CUSIP}
    assert records[CUSIP]["identifiers"] == {"cusip": CUSIP, "isin": [ONE]}
    assert records[ONE]["identifiers"] == {"isin": ONE}


def test_under_the_files_policy_nport_masters_its_securities(database, tmp_path):
    """Ticket 138, switched on 2026-10-26 12:24 ET ("Do limited testing and switch on"):
    under the repo's own policy N-PORT's two Security rules are on. The CUSIP record and
    the ISIN-only record of the ISIN filed with it are one Security; no ISIN is on two."""
    records = prepared_records(tmp_path)
    with database.admin.begin() as conn:
        register_dataset(conn, CODE, database.registry, files.mdm_contract(cusip.NAME, CODE))
        policy = register_policy(conn, files.policy())
    cusip.apply(MergeStage(Store(database.application)), policy, "q2", records, 1)
    with database.application.connect() as conn:
        bound = dict(conn.execute(text("SELECT record_key, entity_id::text FROM mdm.stage_record "
                                       "WHERE source_code = :s AND entity_id IS NOT NULL"), {"s": CODE}).all())
    assert bound[CUSIP] == bound[ONE] and bound[TWO] not in (None, bound[CUSIP])
    securities = [v for v in core.documents(database, "entity").values() if v["kind"] == "security"]
    held = [i for s in securities for i in s.get("identifiers", {}).get("isin", [])]
    assert len(held) == len(set(held))
