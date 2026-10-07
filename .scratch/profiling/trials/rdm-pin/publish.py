"""Ticket 02, last step: publish the place-code table as RDM `sec-place-codes`
version 1 through the real path (import, approve, publish) on a disposable
local PG16, and write its files where the Mastering Policy pins them.

    PATH=<folder with a docker stand-in>:$PATH uv run --extra mdm python \
        .scratch/profiling/trials/rdm-pin/publish.py <out> "<operator>" "<their words>"

There is no hosted RDM yet (production hosting is a later program), so this
sandbox publish is the version's only home; the files are its record.
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[4]))

from edgar_warehouse.rdm import cli  # noqa: E402
from edgar_warehouse.rdm.database import migrate  # noqa: E402
from edgar_warehouse.rdm.store import RDM  # noqa: E402
from tests.integration.test_rdm_postgres import server  # noqa: E402

out, by, words = Path(sys.argv[1]), sys.argv[2], sys.argv[3]
with server() as engine:
    migrate(engine("rdm"), runtime_role="rdm_runtime")
    store = RDM(engine("rdm", "rdm_runtime"))
    imported = cli.import_reference(store, argparse.Namespace(
        name="sec-place-codes", key="codes", label="place", code_set=None,
        set_name="EDGAR state and country codes", version="1",
        created_by="claude/data-profiling (profiling ticket 02)",
        crosswalk=["iso=iso-3166@outside:exact", "type=sec-place-types@1:broad"],
        definition="The codes a filer writes for its state or country of incorporation and of each address",
        used_in=["mdm:company:state_of_incorporation:upper_trimmed",
                 "source:sec.submissions.company:stateOfIncorporation",
                 "source:sec.submissions.company:addresses.stateOrCountry",
                 "source:sec.submissions.company:addresses.countryCode"],
        hint=["meaning=A US state or territory reads as its postal code; X1 is the United States with no state; XX is unknown",
              "use_when=Turning a filer's state or country code into an ISO 3166 jurisdiction (the iso-3166 crosswalk)",
              "avoid_when=Judging a place by its label alone: labels are SEC's own spellings"]))
    approved = {}
    for code_set in ("sec-place-types", "sec-place-codes"):
        store.approve(code_set, "1", by=by, words=words)
        approved[code_set] = store.publish(code_set, "1", out=out)
        assert store.verify(code_set, "1")["matches"]
print(json.dumps({"imported": imported, "published": approved}, indent=2, default=str))
