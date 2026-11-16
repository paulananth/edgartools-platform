"""A Security's ticker names its SEC issuer through the SEC's own ticker file (operator, 2026-11-16: "Accept
recommendation"; ticket 248): the record carries the issuer CIK that file maps its ticker to, and the contract states
`ISSUED_BY` to that SEC Company. Invented values."""
import copy

from edgar_warehouse.mdm.adapters import normalize
from edgar_warehouse.mdm.evidence import subject_key
from edgar_warehouse.rules import files
from tests.mdm.test_identifier_lists import figi

PUBLICATION = {"publication_key": "p1", "revision": 1, "artifact_sha256": "a" * 64, "member": "security",
               "effective_at": None}
CUSIP = "037833100"  # a valid CUSIP check digit


def contract():
    return copy.deepcopy(files.source("openfigi")["dataset_contracts"]["openfigi.security.v4"]["contract"])


def record(**more):
    return {"id": CUSIP, "found": "found", "cusip": CUSIP, "figis": [figi("00TSTX01")], "name": "INVENTED CO",
            "ticker": "INVD", **more}


def read(raw):
    return normalize(raw, source_code="openfigi.security.v4", contract=contract(), publication=PUBLICATION,
                     policy=files.policy())


def test_a_ticker_the_sec_file_maps_to_one_cik_states_the_securitys_issuer():
    body = read(record(issuer_cik="0000051143", issuer_seen="2026-09-02"))
    (link,) = body["relationships"]
    assert (link["type"], link["target_subject"]) == ("ISSUED_BY", subject_key("sec.company.v1", "0000051143"))
    assert link["valid_from"].startswith("2026-09-02") and link["valid_from_basis"] == "observed"


def test_a_ticker_the_sec_file_does_not_map_states_no_issuer():
    assert read(record())["relationships"] == []
