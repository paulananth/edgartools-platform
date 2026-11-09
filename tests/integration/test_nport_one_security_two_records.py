"""Real PG16: two N-PORT records of one Security give it one issuer link (ticket 127).

Ticket 138 ended the fold of an ISIN-only holding into its CUSIP by FIGI: a CUSIP's
holdings and an ISIN-only holding are two records, and MDM finds the one Security for
either. This pins what the Security's ISSUED_BY link is then: its start when both records
name the issuer (the earliest filing), and its links when they name two issuers (none, and a review).
Invented values only.
"""

from __future__ import annotations

import zipfile
from pathlib import Path

from edgar_warehouse.bookkeeping.clean.artifacts import Artifacts
from edgar_warehouse.rules import files
from tests.integration import test_mdm_postgres as core
from tests.integration import test_nport_link_start as link
from tests.support import masters

LEI_OTHER = "9999000000EXAMPLE032"  # invented; the check digits are not needed to name a second issuer
ISIN = "ZZ0000000099"  # invented, check digit valid
CUSIP = "ZZ0000013"
COLUMNS = link.COLUMNS


def capture(root: Path, holdings, identifiers, filings) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    path = root / "nport.zip"
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("FUND_REPORTED_HOLDING.tsv", "\n".join("\t".join(r) for r in [COLUMNS, *holdings]) + "\n")
        z.writestr("IDENTIFIERS.tsv", "HOLDING_ID\tIDENTIFIER_ISIN\n" + "".join(f"{h}\t{i}\n" for h, i in identifiers))
        z.writestr("SUBMISSION.tsv", "ACCESSION_NUMBER\tFILING_DATE\n" + "".join(f"{a}\t{d}\n" for a, d in filings.items()))
    return path


def records(root: Path, holdings, identifiers, filings):
    store = Artifacts()
    raw = store.put_bytes((root / "capture.zip").as_uri(), capture(root, holdings, identifiers, filings).read_bytes())
    pairs = [[h, i] for h, i in identifiers]  # the holding-to-ISIN pair set (ticket 91)
    held = link.read(store, root / "holdings", "source.yaml", raw, link.Q2, lookups={"isin": pairs})
    issued = link.issuers(store, root, raw, pairs, link.Q2, ())
    return link.security_records(store, root, held, issued, batch_id="check-two-records")


def two_records(tmp_path, second_lei: str, second_filing: str):
    """A CUSIP holding (with its ISIN) filed 5 June, and an ISIN-only holding filed `second_filing`."""
    holdings = [["A-1", "1", "Example Corp", link.LEI, "Common", CUSIP],
                ["A-2", "2", "Example Corp", second_lei, "Common", ""]]
    return records(tmp_path, holdings, [("1", ISIN), ("2", ISIN)], {"A-1": "05-JUN-2026", "A-2": second_filing})


def live_securities(database):
    return [v for v in masters.bodies(database.application).values()
            if v["kind"] == "security" and v.get("status") != "alias"]


def test_the_records_of_one_security_give_it_one_link_starting_at_the_earliest_filing(database, tmp_path):
    made = two_records(tmp_path, link.LEI, "28-MAY-2026")
    assert len(made) == 2  # the ISIN-only record, and the CUSIP's, which carries the same ISIN
    policy = link.mastered_issuer(database)
    masters.seed(database.application, made, policy)
    assert len(live_securities(database)) == 1
    (only,) = link.issued_by(database, policy)
    assert link.starts(only) == [(link.MAY28, "observed")]


def test_records_of_one_security_naming_two_issuers_give_it_no_link_and_a_review(database, tmp_path):
    made = two_records(tmp_path, LEI_OTHER, "28-MAY-2026")
    policy = link.mastered_issuer(database)
    # The second issuer is mastered too, as the first is.
    masters.seed(database.application, [core.source(key="custodian2", source_code=link.ADV, fields={"name": "Other Corp"},
                                                    identifiers={"lei": LEI_OTHER})], policy)
    masters.seed(database.application, [core.source(key=LEI_OTHER, source_code=link.GLEIF, fields={"name": "Other Corp"},
                                                    identifiers={"lei": LEI_OTHER},
                                                    provenance={"matching": {"nport_issuer": True}})], policy)
    masters.seed(database.application, made, policy)
    assert len(live_securities(database)) == 1
    # A Security has one issuer (relationship types version 3): neither link stands, and a review asks.
    edges, waiting = masters.link_run(database.application, policy, "2026-10-16T00:00:00+00:00")
    assert not [edge for edge in edges if edge["type"] == "ISSUED_BY"]
    assert "conflicting_targets" in waiting
