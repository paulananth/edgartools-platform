"""A record whose CUSIP fails its check digit joins the Security its ISIN names, on each engine under the real rules."""

from edgar_warehouse.mastering import merge
from tests.storage_adapters.test_mastering import NPORT, SECURITY, live, opened, record
from tests.unit.test_invalid_cusip import BAD, GOOD, read

ISIN = "US0378331005"


def test_a_bad_cusip_record_joins_the_security_its_isin_names(database_factory):
    with opened(database_factory) as db:
        held = record(NPORT, GOOD, "security", cusip=GOOD, isin=ISIN)
        merge.merge_file(db, SECURITY, [held])
        (golden_id, _), = live(db).items()
        bad = read(cusip=BAD, isin=ISIN)  # through the real Dataset Contract: the CUSIP is set aside, the ISIN kept
        merge.merge_file(db, SECURITY, [bad])
        assert list(live(db)) == [golden_id]  # no second Security
        assert db.bound([bad["subject"]])[bad["subject"]] == golden_id
