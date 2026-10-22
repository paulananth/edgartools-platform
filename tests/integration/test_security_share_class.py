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
from edgar_warehouse.mdm.clean import quality
from edgar_warehouse.rules import files
from tests.integration import test_nport_link_start as nport
from tests.support import source_chain as chain

# Invented CUSIPs, check digits valid.
CLASS_A, PLAIN, TWO, TRANCHE, BARE = "ZZ0000013", "ZZ0000021", "ZZ0000039", "ZZ0000047", "ZZ0000054"
TITLES = [(CLASS_A, "CAP STK CL A"), (CLASS_A, "Class A Common Stock"), (PLAIN, "COM"),
          (TWO, "CL A"), (TWO, "SHS CL C"), (BARE, "CAP STK CL"), (BARE, "CLASS AB COM")]


def classes(records: list[dict]) -> dict[str, str | None]:
    return {r["provenance"]["record_key"]: (r["fields"].get("share_class") or {}).get("value") for r in records}


def nport_records(root: Path) -> list[dict]:
    """The N-PORT chain over equity holdings, and one bond tranche titled by class."""
    rows = [[f"A-{n}", str(n), "Example Corp", "", title, cusip, "EC"] for n, (cusip, title) in enumerate(TITLES)]
    rows.append(["A-9", "9", "Example Trust", "", "2021-1 CL A", TRANCHE, "ABS-O"])
    root.mkdir(parents=True, exist_ok=True)
    zipped = root / "nport.zip"
    with zipfile.ZipFile(zipped, "w") as z:
        z.writestr("FUND_REPORTED_HOLDING.tsv",
                   "\n".join("\t".join(r) for r in [[*nport.COLUMNS, "ASSET_CAT"], *rows]) + "\n")
        z.writestr("IDENTIFIERS.tsv", "HOLDING_ID\tIDENTIFIER_ISIN\n")
        z.writestr("SUBMISSION.tsv", "ACCESSION_NUMBER\tFILING_DATE\n")
    store = Artifacts()
    raw = store.put_bytes((root / "capture.zip").as_uri(), zipped.read_bytes())
    holdings = nport.read(store, root / "holdings", "source.yaml", raw, nport.Q2, lookups={"isin": []})
    issuers = nport.issuers(store, root, raw, [], nport.Q2)
    securities = nport.combine(store, root / "reduce", "reduce.yaml", {"holdings": holdings})
    reduced = nport.combine(store, root / "issuer-reduce", "issuer-reduce.yaml", {"issuers": issuers})
    attached = store.put(root.as_uri(), {"version": 1, "artifacts": [
        {"input": raw, "tables": {"attached": []}, "deferred": []}]})
    folded = nport.combine(store, root / "fold", "fold.yaml", {"securities": securities, "attached": attached, "issuers": reduced})
    combined = nport.combine(store, root / "combine", "combine.yaml",
                             {"securities": securities, "attached": attached, "issuers": reduced, "folded": folded})
    prepared = chain.prepare(store, root / "mdm", nport.recorded(store, root / "record", combined), {
        "table": "security", "record_column": "record", "dataset": nport.CODE, "policy": "0" * 64,
        "consumer": "check", "batch_id": "check-class", "as_of": "2026-10-16T00:00:00+00:00"})
    return chain.records(store, root / "mdm", prepared, nport.CODE, files.source(nport.NAME)["mdm"][nport.CODE]["contract"])


THIRTEENF, THIRTEENF_CODE = "sec.thirteenf.information_table", "sec.thirteenf.information_table.security.v1"


def thirteenf_records(root: Path) -> list[dict]:
    """The 13F chain over one information table: every title is a class's evidence."""
    folder = files.ROOT / "sources" / THIRTEENF
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
    assert quality.counts(records, []).get("flagged:share_class_one_letter") == 1


def test_thirteenf_names_the_one_class_its_titles_agree_on(tmp_path):
    records = thirteenf_records(tmp_path)
    assert classes(records) == {CLASS_A: "A", PLAIN: None, TWO: None, BARE: None}
    flagged = [r["provenance"]["record_key"] for r in records
               if "share_class_one_letter" in ((r["provenance"].get("quality") or {}).get("flags") or [])]
    assert flagged == [TWO]
