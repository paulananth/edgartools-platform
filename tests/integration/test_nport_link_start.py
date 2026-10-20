"""Real PG16: an N-PORT ISSUED_BY link starts at its filing (tickets 100, 113).

The real chain on invented holdings: the holdings, issuer and filing source
extracts, reduce.yaml, issuer-reduce.yaml, combine.yaml, mdm.prepare, the
Dataset Contract, then the Merge Stage on a disposable PostgreSQL 16. The
ISSUED_BY link states as its start the earliest filing date of the holdings
that name its issuer (operator, 2026-10-19: "use the filing date or quarter
date or inception date"); the quarter dates nothing in MDM ("if at all it
should be captured in silver not on mdm"); a later quarter keeps the start and
a backfilled earlier one moves it back ("if issued by already exist do not
overight"; "Keep the earlier date"). Invented values only.
"""

from __future__ import annotations

import json
import zipfile
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import text

from edgar_warehouse.bookkeeping.clean.artifacts import Artifacts
from edgar_warehouse.mdm.clean.evidence import subject_key
from edgar_warehouse.mdm.clean.merge import MergeStage
from edgar_warehouse.mdm.clean.store import Store, register_policy
from edgar_warehouse.rules import files
from tests.integration import test_clean_mdm_postgres as core
from tests.mdm import policy_layers
from tests.support import source_chain as chain
from tests.support.rules_authority import register_dataset


NAME, CODE, GLEIF, ADV = "sec.nport.security", "sec.nport.security.v2", "gleif.level1.v1", "iapd.adv.custodians.v1"
FOLDER = files.ROOT / "sources" / NAME
LEI = "9999000000EXAMPLE016"  # invented, check digits valid
COLUMNS = ["ACCESSION_NUMBER", "HOLDING_ID", "ISSUER_NAME", "ISSUER_LEI", "ISSUER_TITLE", "ISSUER_CUSIP"]
HOLDINGS = [["A-1", "1", "Example Corp", LEI, "Common", "ZZ0000013"],
            ["A-2", "2", "Example Corp", LEI, "Common", "ZZ0000013"],
            ["A-1", "3", "Other Inc", "", "Common", "ZZ0000021"]]
# Each filing's date as SEC writes it; the link starts at the earlier, 28 May.
FILINGS = {"A-1": "05-JUN-2026", "A-2": "28-May-2026"}
Q2, Q3 = "2026-06-30T00:00:00+00:00", "2026-09-30T00:00:00+00:00"
MAY28, AUG14 = "2026-05-28T00:00:00+00:00", "2026-08-14T00:00:00+00:00"


def capture(root: Path, holdings: list[list[str]], filings: dict[str, str] = FILINGS) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    path = root / "nport.zip"
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("FUND_REPORTED_HOLDING.tsv", "\n".join("\t".join(r) for r in [COLUMNS, *holdings]) + "\n")
        z.writestr("IDENTIFIERS.tsv", "HOLDING_ID\tIDENTIFIER_ISIN\n")
        z.writestr("SUBMISSION.tsv", "ACCESSION_NUMBER\tFILING_DATE\n"
                   + "".join(f"{a}\t{d}\n" for a, d in filings.items()))
    return path


def read(store, root, contract_file, raw, period, lookups=None):
    root.mkdir(parents=True, exist_ok=True)
    body = {"source": NAME, **files.load(FOLDER / contract_file)}
    context = store.put(root.as_uri(), {"version": 1, "input": raw, "values": {"period": period} if period else {}})
    entry = {"input": raw, "context": context}
    if lookups is not None:
        entry["lookups"] = store.put(root.as_uri(), {"version": 1, "input": raw, "sets": lookups})
    return chain.read(store, root, body, [entry], 3 if lookups is not None else 2)


def combine(store, root, contract_file, readings):
    return chain.combine(store, root, FOLDER / contract_file, readings)


def recorded(store, root, combined):
    """record.yaml over the combine's pieces (ticket 120): each Security row as its
    record, a row folded into a CUSIP's Security left out."""
    root.mkdir(parents=True, exist_ok=True)
    pieces = [store.put(root.as_uri(), {"tables": a["tables"]}) for a in store.json(combined)["artifacts"]]
    return chain.read(store, root, files.load(FOLDER / "record.yaml"), [
        {"input": p, "context": store.put(root.as_uri(), {"version": 1, "input": p, "values": {}})} for p in pieces], 2)


def filed_pairs(store, root, raw) -> list[list[str]]:
    """Each filing's accession and date (filings.yaml), the issuer reading's `filed` set."""
    reading = read(store, root / "filings", "filings.yaml", raw, None)
    rows = [row for artifact in store.json(reading)["artifacts"] for part in artifact.get("partitions", [])
            for row in store.json(part["receipt"])["tables"]["filed"]]
    rows += [row for artifact in store.json(reading)["artifacts"] for row in artifact.get("tables", {}).get("filed", [])]
    return [[row["accession"], row["filed"]] for row in rows if row["filed"]]


def issuers(store, root, raw, isin, period, umbrella=()):
    """The issuer source extract, each holding with its filing's date, else the quarter's."""
    return read(store, root / "issuers", "issuers.yaml", raw, period,
                lookups={"isin": isin, "umbrella": list(umbrella), "filed": filed_pairs(store, root, raw)})


def prepared_records(root: Path, period: str, revision: int | None = None,
                     rows: list[list[str]] = HOLDINGS, umbrella: tuple[list[str], ...] = (),
                     filings: dict[str, str] = FILINGS) -> list[dict]:
    """The quarter's Security assertions, through the real chain; `umbrella`
    pairs each fund LEI with the trust it is a sub-fund of."""
    store = Artifacts()
    zipped = capture(root, rows, filings)
    raw = store.put_bytes((root / "capture.zip").as_uri(), zipped.read_bytes())
    holdings = read(store, root / "holdings", "source.yaml", raw, period, lookups={"isin": []})
    issuer_reading = issuers(store, root, raw, [], period, umbrella)
    securities = combine(store, root / "reduce", "reduce.yaml", {"holdings": holdings})
    reduced = combine(store, root / "issuer-reduce", "issuer-reduce.yaml", {"issuers": issuer_reading})
    attached = store.put(root.as_uri(), {"version": 1, "artifacts": [
        {"input": raw, "tables": {"attached": []}, "deferred": []}]})
    folded = combine(store, root / "fold", "fold.yaml", {"securities": securities, "attached": attached, "issuers": reduced})
    combined = combine(store, root / "combine", "combine.yaml",
                       {"securities": securities, "attached": attached, "issuers": reduced, "folded": folded})
    prepared = chain.prepare(store, root / "mdm", recorded(store, root / "record", combined), {
        "table": "security", "record_column": "record", "dataset": CODE, "policy": "0" * 64, "consumer": "check",
        "batch_id": f"check-{period[:10]}", "as_of": "2026-10-16T00:00:00+00:00",
        # The quarter dates nothing in MDM (ticket 113); quarters that follow
        # one another are revisions of one publication (ticket 101).
        **({} if revision is None else {"publication_key": f"nport:{period[:10]}", "revision": str(revision)})})
    return chain.records(store, root / "mdm", prepared, CODE, files.source(NAME)["mdm"][CODE]["contract"])


def policy_body() -> dict:
    # The ADV custodian LEI rule (ticket 76) and the N-PORT Security rules (ticket 79) are on in
    # the live policy; the issuer LEI rule is switched on here for the test only.
    return policy_layers.with_rules_on(files.policy(), "company", "gleif-issuer-lei")


def apply(stage, policy, batch, assertions, checkpoint):
    stage.apply(batch_id=batch, run_id=str(uuid4()), policy_digest=policy, consumer="check",
                expected_checkpoint=checkpoint - 1, checkpoint=checkpoint, as_of="2026-10-16T00:00:00+00:00",
                assertions=assertions)


def mastered_issuer(database):
    """The policy registered, and the issuer's Company: an ADV custodian gives it
    the LEI, and the issuer's GLEIF record joins it."""
    for code in (ADV, GLEIF):
        core.register_reading(database, code, core.contract_body())
    with database.admin.begin() as conn:
        register_dataset(conn, CODE, database.registry, files.mdm_contract(NAME, CODE))
        policy = register_policy(conn, policy_body())
    stage = MergeStage(Store(database.application))
    apply(stage, policy, "custodian", [core.source(key="custodian", source_code=ADV, fields={"name": "Example Corp"},
                                                   identifiers={"lei": LEI})], 1)
    apply(stage, policy, "gleif", [core.source(key=LEI, source_code=GLEIF, fields={"name": "Example Corp"},
                                               identifiers={"lei": LEI},
                                               provenance={"matching": {"nport_issuer": True}})], 2)
    return stage, policy


def issued_by(database):
    with database.application.connect() as conn:
        return conn.execute(text(
            "SELECT body->'periods', body->>'last_seen' FROM mdm.current_record WHERE object_type='relationship' "
            "AND body->>'type'='ISSUED_BY'")).all()


def starts(database):
    ((periods, _),) = issued_by(database)
    return [(p["valid_from"], p["valid_from_basis"]) for p in periods]


def test_an_issued_by_link_starts_at_its_earliest_filing(database, tmp_path):
    q2 = prepared_records(tmp_path / "q2", Q2)
    linked = [r for r in q2 if any(l["type"] == "ISSUED_BY" for l in r.get("relationships") or [])]
    assert len(q2) == 2 and len(linked) == 1
    stage, policy = mastered_issuer(database)
    apply(stage, policy, "q2", q2, 3)
    with database.application.connect() as conn:
        reviews = conn.execute(text("SELECT body->>'reason' FROM mdm.current_record WHERE object_type='review' "
                                    "AND body->'open'='true'::jsonb")).scalars().all()
    assert "unknown_relationship_start" not in reviews
    assert starts(database) == [(MAY28, "stated")]


def test_a_later_quarter_keeps_the_start(database, tmp_path):
    q2 = prepared_records(tmp_path / "q2", Q2, revision=20262)
    q3 = prepared_records(tmp_path / "q3", Q3, revision=20263, filings={"A-1": "14-AUG-2026", "A-2": "14-AUG-2026"})
    stage, policy = mastered_issuer(database)
    apply(stage, policy, "q2", q2, 3)
    apply(stage, policy, "q3", q3, 4)
    assert starts(database) == [(MAY28, "stated")]


def test_a_backfilled_earlier_quarter_moves_the_start_back(database, tmp_path):
    q3 = prepared_records(tmp_path / "q3", Q3, revision=20262, filings={"A-1": "14-AUG-2026", "A-2": "14-AUG-2026"})
    q2 = prepared_records(tmp_path / "q2", Q2, revision=20263)
    stage, policy = mastered_issuer(database)
    apply(stage, policy, "q3", q3, 3)
    assert starts(database) == [(AUG14, "stated")]
    apply(stage, policy, "q2", q2, 4)
    assert starts(database) == [(MAY28, "stated")]


def test_a_holding_with_no_filing_date_starts_at_the_quarter(database, tmp_path):
    q2 = prepared_records(tmp_path / "q2", Q2, filings={})
    stage, policy = mastered_issuer(database)
    apply(stage, policy, "q2", q2, 3)
    assert starts(database) == [(Q2, "stated")]


def test_a_filing_date_of_another_shape_is_none(tmp_path):
    store = Artifacts()
    filings = {"A-1": "5-JUN-2026", "A-2": "28-May-26"}
    raw = store.put_bytes((tmp_path / "capture.zip").as_uri(), capture(tmp_path, HOLDINGS, filings).read_bytes())
    assert filed_pairs(store, tmp_path, raw) == []


def test_an_issuer_reading_with_no_quarter_is_refused(tmp_path):
    store = Artifacts()
    raw = store.put_bytes((tmp_path / "capture.zip").as_uri(), capture(tmp_path, HOLDINGS).read_bytes())
    with pytest.raises(Exception, match="context keys differ from the declared fields"):
        issuers(store, tmp_path, raw, [], None)


def test_a_fund_series_counts_as_its_umbrella_trust(tmp_path):
    """Ticket 23 (operator, 2026-10-17: "Umbrella trust (Recommended)"): holdings
    naming a fund series and its trust give one issuer, the trust; without the
    pair the two LEIs leave the Security with no link."""
    trust = "9999000000EXAMPLE113"  # invented
    holdings = [["A-1", "1", "Example Fund", LEI, "ETF", "ZZ0000013"],
                ["A-1", "2", "Example Fund", LEI, "ETF", "ZZ0000013"],
                ["A-2", "3", "Example Trust", trust, "ETF", "ZZ0000013"]]
    pairs = ([LEI, trust],)
    (linked,) = prepared_records(tmp_path / "with", Q2, rows=holdings, umbrella=pairs)
    def targets(record):
        return [l["target_subject"] for l in record.get("relationships") or [] if l["type"] == "ISSUED_BY"]

    assert targets(linked) == [subject_key(GLEIF, trust)]
    (unpaired,) = prepared_records(tmp_path / "without", Q2, rows=holdings)
    assert targets(unpaired) == []
