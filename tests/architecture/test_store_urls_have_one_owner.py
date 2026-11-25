"""A duty file holds one URL a database, and one module knows their names: every other piece of code asks
`edgar_warehouse.database_connections` (store_url, configured, instance_url, url_variable). Operator: "kiss 94 url will be
nigthmree to maintain"."""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
NAMES = re.compile(r"\b(DATA_URL|CONTROL_URL|CONFIG_URL|DB_URL)\b")
# The resolver, and the two stores that ship alone and read their one URL themselves.
OWNERS = {
    "edgar_warehouse/database_connections.py",
    "edgar_warehouse/bookkeeping/clean/database.py",
    "edgar_warehouse/change_journal/store.py",
}
CODE = ("edgar_warehouse", "skills", "infra/scripts", "scripts")


def offenders() -> list[str]:
    found = []
    for top in CODE:
        for path in sorted((ROOT / top).rglob("*")):
            if path.suffix not in {".py", ".sh"} or "/tests/" in str(path) or not path.is_file():
                continue
            relative = str(path.relative_to(ROOT))
            if relative in OWNERS:
                continue
            for number, line in enumerate(path.read_text(errors="ignore").splitlines(), 1):
                if NAMES.search(line):
                    found.append(f"{relative}:{number}")
    return found


def test_only_the_resolver_names_a_store_url():
    assert offenders() == []
