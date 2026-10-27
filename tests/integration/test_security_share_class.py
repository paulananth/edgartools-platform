"""A Security's share class from its filed titles (ticket 130).

The real chain on invented holdings, for 13F and N-PORT: the source extract,
the reduction, the combine, mdm.prepare and the Dataset Contract. The class is
the one letter after CL, CLASS or CLS in the filed titles (operator,
2026-10-22: "Approve the rule (Recommended)"); titles that name two letters
give none and are flagged for a steward; a title naming none gives none; in
N-PORT only equity holdings name a class. Invented values only.
"""

from __future__ import annotations

import zipfile
from pathlib import Path


from edgar_warehouse.bookkeeping.clean.artifacts import Artifacts
from tests.integration import test_clean_mdm_postgres as core
from edgar_warehouse.mdm.clean.merge import MergeStage
from edgar_warehouse.mdm.clean.store import Store, register_policy
from edgar_warehouse.rules import files
from tests.integration import test_nport_link_start as nport
from tests.support import source_chain as chain
from tests.support.rules_authority import register_dataset

# Invented CUSIPs, check digits valid.
CLASS_A, PLAIN, TWO, TRANCHE, BARE = "ZZ0000013", "ZZ0000021", "ZZ0000039", "ZZ0000047", "ZZ0000054"
TITLES = [(CLASS_A, "CAP STK CL A"), (CLASS_A, "Class A Common Stock"), (PLAIN, "COM"),
          (TWO, "CL A"), (TWO, "SHS CL C"), (BARE, "CAP STK CL"), (BARE, "CLASS AB COM")]


def classes(records: list[dict]) -> dict[str, str | None]:
    return {r["provenance"]["record_key"]: (r["fields"].get("share_class") or {}).get("value") for r in records}


# Invented ISINs, check digits valid; SECOND is an ISIN-only holding's, and the CUSIP
# MIXED's own holdings name two letters.
ISIN_ONLY, SECOND, MIXED = "ZZ0000000016", "ZZ0000000024", "ZZ0000062"


def flagged(records: list[dict]) -> list[str]:
    return sorted(r["provenance"]["record_key"] for r in records
                  if "share_class_one_letter" in ((r["provenance"].get("quality") or {}).get("flags") or []))


def nport_records(root: Path, extra: list[list[str]] = (), pairs: list[list[str]] = ()) -> list[dict]:
    """The N-PORT chain over equity holdings, and one bond tranche titled by class;
    `pairs` gives a holding its ISIN."""
    rows = [[f"A-{n}", str(n), "Example Corp", "", title, cusip, "EC"] for n, (cusip, title) in enumerate(TITLES)]
    rows.append(["A-9", "9", "Example Trust", "", "2021-1 CL A", TRANCHE, "ABS-O"])
    rows += extra
    root.mkdir(parents=True, exist_ok=True)
    zipped = root / "nport.zip"
    with zipfile.ZipFile(zipped, "w") as z:
        z.writestr("FUND_REPORTED_HOLDING.tsv",
                   "\n".join("\t".join(r) for r in [[*nport.COLUMNS, "ASSET_CAT"], *rows]) + "\n")
        z.writestr("IDENTIFIERS.tsv", "HOLDING_ID\tIDENTIFIER_ISIN\n")
        z.writestr("SUBMISSION.tsv", "ACCESSION_NUMBER\tFILING_DATE\n")
    store = Artifacts()
    raw = store.put_bytes((root / "capture.zip").as_uri(), zipped.read_bytes())
    holdings = nport.read(store, root / "holdings", "source.yaml", raw, nport.Q2, lookups={"isin": list(pairs)})
    issuers = nport.issuers(store, root, raw, list(pairs), nport.Q2)
    return nport.security_records(store, root, holdings, issuers, batch_id="check-class")


THIRTEENF, THIRTEENF_CODE = "sec.thirteenf.information_table", "sec.thirteenf.information_table.security.v1"


def thirteenf_records(root: Path, rows: str | None = None) -> list[dict]:
    """The 13F chain over one information table (`rows`, its infoTable elements):
    by default every title is a class's evidence."""
    folder = files.ROOT / "sources" / THIRTEENF
    if rows is None:
        rows = "".join(f"<infoTable><nameOfIssuer>EXAMPLE CORP</nameOfIssuer><titleOfClass>{title}</titleOfClass>"
                       f"<cusip>{cusip}</cusip><value>1</value></infoTable>" for cusip, title in TITLES)
    root.mkdir(parents=True, exist_ok=True)
    store = Artifacts()
    body = {"source": THIRTEENF, **files.load(folder / "source.yaml")}

    def unit(n: int, table: str) -> dict:
        raw = store.put_bytes((root / f"table-{n}.xml").as_uri(), f"<informationTable>{table}</informationTable>".encode())
        context = store.put(root.as_uri(), {"version": 1, "input": raw, "values": {}})
        return chain.read(store, root / f"read-{n}", body, [{"input": raw, "context": context}], 2)

    # The run's eight reading units; one holds the table, the others none.
    units = {f"units_{n}": unit(n, rows if n == 1 else "") for n in range(1, 9)}
    securities = chain.combine(store, root / "reduce", folder / "reduce.yaml", units)
    combined = chain.combine(store, root / "combine", folder / "combine.yaml", {"securities": securities})
    prepared = chain.prepare(store, root / "mdm", combined, {
        "table": "security", "dataset": THIRTEENF_CODE, "policy": "0" * 64,
        "consumer": "check", "batch_id": "check-class", "as_of": "2026-10-16T00:00:00+00:00"})
    return chain.records(store, root / "mdm", prepared, THIRTEENF_CODE,
                         files.source(THIRTEENF)["mdm"][THIRTEENF_CODE]["contract"])


def test_nport_names_the_one_class_its_equity_titles_agree_on(tmp_path):
    records = nport_records(tmp_path)
    assert classes(records) == {CLASS_A: "A", PLAIN: None, TWO: None, TRANCHE: None, BARE: None}
    assert flagged(records) == [TWO]


def test_nport_an_isin_only_security_and_a_cusip_take_their_own_levels_class(tmp_path):
    """An ISIN-only equity holding names its own record's class; a CUSIP whose own
    holdings name two letters gets none. Each ISIN-only holding keeps its own record
    (ticket 138: no fold into a CUSIP's row)."""
    extra = [["A-20", "20", "Example Corp", "", "CL B", "", "EC"],
             ["A-21", "21", "Example Corp", "", "CL A", MIXED, "EC"],
             ["A-22", "22", "Example Corp", "", "CL C", MIXED, "EC"],
             ["A-23", "23", "Example Corp", "", "CL A", "", "EC"]]
    pairs = [["20", ISIN_ONLY], ["23", SECOND]]
    records = nport_records(tmp_path, extra, pairs)
    found = classes(records)
    assert (found[ISIN_ONLY], found[MIXED], found[SECOND]) == ("B", None, "A")
    assert flagged(records) == [TWO, MIXED]


def test_thirteenf_names_the_one_class_its_titles_agree_on(tmp_path):
    records = thirteenf_records(tmp_path)
    assert classes(records) == {CLASS_A: "A", PLAIN: None, TWO: None, BARE: None}
    assert flagged(records) == [TWO]


def test_the_mastered_security_carries_its_class(database, tmp_path):
    """The Merge Stage on a disposable PostgreSQL 16: the Security takes the letter
    as a field; the Securities its titles name none or two of have none."""
    records = nport_records(tmp_path)
    with database.admin.begin() as conn:
        register_dataset(conn, nport.CODE, database.registry, files.mdm_contract(nport.NAME, nport.CODE))
        # N-PORT's Security rules wait for their switch-on (ticket 138); on here, for the test only.
        policy = register_policy(conn, nport.policy_body())
    nport.apply(MergeStage(Store(database.application)), policy, "class", records, 1)
    rows = [(body["identifiers"]["cusip"][0], body.get("fields", {}).get("share_class"))
            for body in core.documents(database, "entity").values() if body["kind"] == "security"]
    mastered = {cusip: (value.get("value") if isinstance(value, dict) else value) for cusip, value in rows}
    assert mastered == {CLASS_A: "A", PLAIN: None, TWO: None, TRANCHE: None, BARE: None}
