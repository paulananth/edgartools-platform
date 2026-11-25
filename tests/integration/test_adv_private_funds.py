"""Real PG16: Form ADV's private funds become Fund Structures by PFID, linked to their advisers.

The real chain on one invented monthly Form ADV file: the adviser filings (iapd.adv) and the private
funds of Schedule D 7.B(1) and 7.B(2) (iapd.adv.fund: two source extracts, funds.yaml, combine.yaml,
mdm.prepare), the two Dataset Contracts, then the Merge Stage under the real rules. Operator,
2026-11-24: "Join by PFID only (Recommended)", "Reuse advisor/subadvisor (Recommended)", "Yes,
IS_FEEDER_TO by PFID (Recommended)", "Yes, by PFID (Recommended)". Invented values only.
"""

from __future__ import annotations

import io
import zipfile
from collections import Counter
from pathlib import Path

from edgar_warehouse.bookkeeping.clean.artifacts import Artifacts
from edgar_warehouse.rules import files
from tests.support import masters, source_chain as chain

ADV, FUNDS = "iapd.adv", "iapd.adv.fund"
FILINGS, FUND, FUND_FILING = "iapd.adv.filings.v2", "iapd.adv.fund.v1", "iapd.adv.fund_filing.v1"
JUNE = "2026-06-30T00:00:00+00:00"
BASE = ["FilingID", "DateSubmitted", "1A", "1B1", "1D", "1E1", "1P", "1F1-Street 1", "1F1-Street 2",
        "1F1-City", "1F1-State", "1F1-Country", "1F1-Postal"]
REPORTED = ["FilingID", "Fund Name", "Fund ID", "Master Fund ID", "Subadviser"]
LISTED = ["FilingID", "Fund Name", "Fund ID", "Adviser Name", "Adviser SEC Number"]
P1, P2, P3, P4, P5, P6 = (f"805-999990000{n}" for n in range(1, 7))


def filing(filing_id: str, name: str, crd: str, registration: str = "801") -> list[str]:
    return [filing_id, "06/20/2026 10:00:00 AM", name, "", f"{registration}-{crd}" if registration else "", crd, "",
            "1 Example Way", "", "Example City", "NY", "United States", "10001"]


# Adviser A files twice in the month (an amendment, 9000002 after 9000001) and reports funds 1 and 3, and fund 2,
# a feeder of fund 3. Adviser B reports fund 1 too, as its subadviser, and lists fund 4, which no 7.B(1) row reports.
FILES = {
    f"IA_ADV_Base_A_{JUNE[:7]}.csv": (BASE, [filing("9000001", "EXAMPLE ADVISERS A LLC", "999101"),
                                             filing("9000002", "EXAMPLE ADVISERS A LLC", "999101"),
                                             filing("9000003", "EXAMPLE ADVISERS B LLC", "999102")]),
    "IA_Schedule_D_7B1_x.csv": (REPORTED, [["9000001", "EXAMPLE FUND ONE LP", P1, "", "N"],
                                           ["9000002", "EXAMPLE FUND ONE LP", P1, "", "N"],
                                           ["9000002", "EXAMPLE FEEDER LP", P2, P3, "N"],
                                           ["9000002", "EXAMPLE MASTER LP", P3, "", "N"],
                                           ["9000003", "EXAMPLE FUND ONE LP", P1, "", "Y"]]),
    "IA_Schedule_D_7B2_x.csv": (LISTED, [["9000003", "EXAMPLE LISTED FUND LP", P4, "EXAMPLE OTHER LLC", "801-99999"]]),
    "IA_Schedule_D_5K3_x.csv": (["Filing ID", "5K(3)(a)", "5K(3)(b)", "5K(3)(c) City", "5K(3)(c) State",
                                 "5K(3)(c) Country", "5K(3)(d)", "5K(3)(e)", "5K(3)(f)", "5K(3)(g)"], []),
    "IA_1D3_CIK_x.csv": (["FilingID", "CIK"], []),
    # The exempt reporting advisers' tables. C (802-) and D (no SEC number) are in them alone; B's filing is registered
    # (801-), so it is in both files, its fund rows too. C reports fund 1 as well, and fund 5; D lists fund 6.
    "ERA_ADV_Base_x.csv": (BASE, [filing("9000003", "EXAMPLE ADVISERS B LLC", "999102"),
                                  filing("9000004", "EXAMPLE ADVISERS C LLC", "999103", "802"),
                                  filing("9000005", "EXAMPLE ADVISERS D LLC", "999104", "")]),
    "ERA_Schedule_D_7B1_x.csv": (REPORTED, [["9000003", "EXAMPLE FUND ONE LP", P1, "", "Y"],
                                            ["9000004", "EXAMPLE FUND ONE LP", P1, "", "N"],
                                            ["9000004", "EXAMPLE ERA FEEDER LP", P5, P3, "N"]]),
    "ERA_Schedule_D_7B2_x.csv": (LISTED, [["9000005", "EXAMPLE ERA LISTED LP", P6, "EXAMPLE OTHER LLC", "801-99999"]]),
    "ERA_1D3_CIK_x.csv": (["FilingID", "CIK"], []),
    "ERA_Schedule_D_7A_CIK_x.csv": (["FilingID", "ReferenceID", "CIK"], []),
    "IA_Schedule_D_7A_CIK_x.csv": (["FilingID", "ReferenceID", "CIK"], []),
}


def csv_text(header: list[str], rows: list[list[str]]) -> str:
    return "\n".join(",".join(f'"{v}"' for v in r) for r in [header, *rows]) + "\n"


def read(store, root: Path, source: str, contract_file: str, raw: dict, dated: bool = True, published: str = JUNE) -> dict:
    root.mkdir(parents=True, exist_ok=True)
    body = {"source": source, "execution": {"profile": "source.read", "workers": 1, "max_artifacts": 1},
            **files.load(files.sources_root() / source / contract_file)}
    context = store.put(root.as_uri(), {"version": 1, "input": raw, "values": {"published": published} if dated else {}})
    return chain.read(store, root, body, [{"input": raw, "context": context}], 2)


def prepare(store, root: Path, source: str, reading: dict, table: str, code: str, published: str, **more) -> list[dict]:
    prepared = chain.prepare(store, root, reading, {
        "table": table, "dataset": code, "policy": "0" * 64, "consumer": "check", "batch_id": f"check-{code}",
        "as_of": "2026-10-16T00:00:00+00:00", "publication_key": f"{source}:{published[:7]}", "revision": published[:7].replace("-", ""),
        "effective_at": published, **more})
    return chain.records(store, root, prepared, code, files.source(source)["dataset_contracts"][code]["contract"])


def month(root: Path, published: str = JUNE, tables: dict = FILES) -> tuple[list[dict], list[dict]]:
    """The month's adviser filing records and private fund records, through the real chain."""
    store = Artifacts()
    root.mkdir(parents=True, exist_ok=True)
    body = io.BytesIO()
    with zipfile.ZipFile(body, "w") as z:
        for name, (header, rows) in tables.items():
            z.writestr(name, csv_text(header, rows))
    raw = store.put_bytes((root / "capture.zip").as_uri(), body.getvalue())
    folder = files.sources_root()
    filings = read(store, root / "filings", ADV, "adviser-filings-csv.yaml", raw, published=published)
    combined = chain.combine(store, root / "adv-combine", folder / ADV / "combine.yaml", {
        "filings": filings, "custody": read(store, root / "custody", ADV, "custody-csv.yaml", raw, published=published),
        "ciks": read(store, root / "ciks", ADV, "ciks-csv.yaml", raw, dated=False),
        "related": read(store, root / "related", ADV, "related-csv.yaml", raw, dated=False),
        "era_filings": read(store, root / "era-filings", ADV, "era-filings-csv.yaml", raw, published=published),
        "era_ciks": read(store, root / "era-ciks", ADV, "era-ciks-csv.yaml", raw, dated=False),
        "era_related": read(store, root / "era-related", ADV, "era-related-csv.yaml", raw, dated=False)})
    readings = {name: read(store, root / name, FUNDS, f"{name.replace('_', '-')}-csv.yaml", raw, published=published)
                for name in ("reported", "listed", "era_reported", "era_listed")}
    reduced = chain.combine(store, root / "funds", folder / FUNDS / "funds.yaml", readings)
    funds = chain.combine(store, root / "fund-combine", folder / FUNDS / "combine.yaml",
                          {"funds": reduced, **readings})
    filing_funds = chain.combine(store, root / "filing-funds", folder / FUNDS / "filing-funds.yaml", readings)
    return (prepare(store, root / "mdm-filings", ADV, combined, "filings", FILINGS, published),
            prepare(store, root / "mdm-funds", FUNDS, funds, "fund", FUND, published)
            + prepare(store, root / "mdm-filing-funds", FUNDS, filing_funds, "filing_fund", FUND_FILING, published,
                      distinct_on=["filing_id", "fund_id"]))


def test_private_funds_join_by_pfid_and_link_to_their_advisers(database, tmp_path):
    advisers, funds = month(tmp_path / "june")
    # One record per fund, the 7.B(2)-only fund included; its name is 7.B(1)'s where one reports it.
    assert sorted(r["record_key"] for r in funds if r["source_code"] == FUND) == [P1, P2, P3, P4, P5, P6]
    # One record per filing: the registered filing that is in both files is read from the registered advisers' alone.
    assert sorted(r["record_key"] for r in advisers) == [f"900000{n}" for n in range(1, 6)]
    names = {r["record_key"]: r["fields"]["name"]["value"] for r in funds if r["source_code"] == FUND}
    assert names[P4] == "EXAMPLE LISTED FUND LP"
    ids = masters.seed(database.application, advisers + funds)
    assert len({ids[k] for k in (P1, P2, P3, P4, P5, P6)}) == 6  # six Fund Structures, one per PFID
    assert masters.reviews(database.application) == []
    named = {name: entity for entity, name in masters.names(database.application).items()}
    a, b, c, d = (named[f"EXAMPLE ADVISERS {x} LLC"] for x in "ABCD")
    # The adviser filings give each adviser's Company the adviser role, which the link needs at its start.
    bodies = masters.bodies(database.application)
    assert [p["role"] for p in bodies[a].get("profiles", [])] == ["adviser"]
    assert [[p["role"] for p in bodies[e].get("profiles", [])] for e in (b, c, d)] == [["adviser"]] * 3
    assert [p["role"] for p in bodies[ids[P4]].get("profiles", [])] == ["fund"]
    advice = masters.links(database.application, of_type="INVESTMENT_ADVISER_TO")
    # A's two filings report fund 1: one link. B reports it as subadviser: a link of its own.
    assert Counter((l["source_id"], l["target_id"], l["capacity"]) for l in advice) == Counter({
        (a, ids[P1], "advisor"): 1, (b, ids[P1], "subadvisor"): 1, (a, ids[P2], "advisor"): 1,
        (a, ids[P3], "advisor"): 1, (b, ids[P4], "advisor"): 1,
        (c, ids[P1], "advisor"): 1, (c, ids[P5], "advisor"): 1, (d, ids[P6], "advisor"): 1})
    feeders = masters.links(database.application, of_type="IS_FEEDER_TO")
    assert sorted((l["source_id"], l["target_id"]) for l in feeders) == sorted([(ids[P2], ids[P3]), (ids[P5], ids[P3])])


def test_an_unchanged_month_loaded_again_changes_nothing(database, tmp_path):
    advisers, funds = month(tmp_path / "june")
    first = masters.seed(database.application, advisers + funds)
    links = masters.links(database.application)
    again = masters.seed(database.application, advisers + funds)
    assert again == first
    assert masters.links(database.application) == links
    assert masters.reviews(database.application) == []


def test_a_later_month_that_names_another_adviser_keeps_the_earlier_advisers_link(database, tmp_path):
    """A fund is one record per PFID, so its July record replaces June's; each filing's own record keeps its link."""
    july = {**FILES, **{name: (header, []) for name, (header, _) in FILES.items()},
            "IA_ADV_Base_A_x.csv": (BASE, [filing("9000009", "EXAMPLE ADVISERS B LLC", "999102")]),
            "IA_Schedule_D_7B1_x.csv": (REPORTED, [["9000009", "EXAMPLE FUND ONE LP", P1, "", "Y"]])}
    del july[f"IA_ADV_Base_A_{JUNE[:7]}.csv"]
    advisers, funds = month(tmp_path / "june")
    ids = masters.seed(database.application, advisers + funds)
    before = {(l["source_id"], l["target_id"], l["capacity"]) for l in masters.links(database.application, of_type="INVESTMENT_ADVISER_TO")}
    advisers, funds = month(tmp_path / "july", "2026-07-31T00:00:00+00:00", july)
    masters.seed(database.application, advisers + funds)
    after = {(l["source_id"], l["target_id"], l["capacity"]) for l in masters.links(database.application, of_type="INVESTMENT_ADVISER_TO")}
    assert after == before and len([link for link in after if link[1] == ids[P1]]) == 3
