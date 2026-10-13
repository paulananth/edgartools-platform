"""Profiling ticket 07: the RDM code set `sec-ownership-transaction-codes`
version 1, drafted from SEC Form 4 General Instruction 8 (the draft file
beside this script), on a disposable local PG16.

Without approval it drafts and prints the sha256 the version would publish
under. With the operator's words it approves and publishes the version and
writes its files where readings pin them:

    PG16_SERVER=pgserver uv run --extra mdm --with pgserver python \
        .scratch/profiling/trials/readers/ownership/codes/publish.py [<out> "<operator>" "<their words>"]

There is no hosted RDM yet, so this sandbox publish is the version's only
home; the files are its record (as `sec-place-codes`, profiling ticket 02).
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[6]))

from edgar_warehouse.rdm import cli  # noqa: E402
from edgar_warehouse.rdm.database import migrate  # noqa: E402
from edgar_warehouse.rdm.store import RDM, sha256  # noqa: E402
from tests.integration.test_rdm_postgres import server  # noqa: E402

DRAFT = Path(__file__).with_name("sec-ownership-transaction-codes.json")
CODE_SET, VERSION = "sec-ownership-transaction-codes", "1"

with server() as engine:
    migrate(engine("rdm"), runtime_role="rdm_runtime")
    store = RDM(engine("rdm", "rdm_runtime"))
    drafted = cli.draft_file(store, DRAFT)
    with store.engine.connect() as conn:
        codes, levels = store._content(conn, CODE_SET, VERSION)
    result = {"drafted": drafted, "sha256": sha256(codes, levels)}
    if len(sys.argv) == 4:
        out, by, words = Path(sys.argv[1]), sys.argv[2], sys.argv[3]
        store.approve(CODE_SET, VERSION, by=by, words=words)
        result["published"] = store.publish(CODE_SET, VERSION, out=out)
        assert store.verify(CODE_SET, VERSION)["matches"]
        assert result["published"]["sha256"] == result["sha256"]
print(json.dumps(result, indent=2, default=str))
