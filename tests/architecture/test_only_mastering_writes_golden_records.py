"""Step 1 of mastering: no source writes a golden record directly (CONTEXT.md, "Mastering").

A golden record is a row of `mastering_master`. Only the mastering store writes it, and only the merge calls the store's
writer. The scan reads the source text, so a second writer anywhere in `edgar_warehouse` fails here, and the scan is
itself tested on a made tree with a rogue writer.
"""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2] / "edgar_warehouse"
WRITE = re.compile(r"(insert\s+into|update|delete\s+from|merge\s+into)\s+mastering_master\b|"
                   r"mastering_master\.\w+\s*<>\s*excluded|mastering_master\.\w+\s*=\s*new\.", re.IGNORECASE)
STORE, MERGE = "mastering/store.py", "mastering/merge.py"


def writers(root: Path) -> tuple[set[str], set[str]]:
    """The files that write `mastering_master`, and the files that call `write_masters(`."""
    tables, callers = set(), set()
    for path in root.rglob("*"):
        if path.suffix not in (".py", ".sql") or "__pycache__" in path.parts:
            continue
        text = path.read_text(errors="ignore")
        relative = path.relative_to(root).as_posix()
        if WRITE.search(text):
            tables.add(relative)
        if re.search(r"\.write_masters\(", text):
            callers.add(relative)
    return tables, callers


def test_only_the_mastering_store_writes_the_golden_record_table():
    tables, _ = writers(ROOT)
    assert tables == {STORE}, f"another file writes mastering_master: {sorted(tables - {STORE})}"


def test_only_the_merge_calls_the_stores_writer():
    _, callers = writers(ROOT)
    assert callers == {MERGE}, f"another file calls write_masters: {sorted(callers - {MERGE})}"


def test_the_scan_finds_a_rogue_writer(tmp_path):
    (tmp_path / "mastering").mkdir()
    (tmp_path / "mastering" / "store.py").write_text('cursor.execute("insert into mastering_master(entity_id) values (1)")')
    (tmp_path / "rogue.py").write_text('db.execute("UPDATE mastering_master SET body = 1")\ndb.write_masters([])')
    tables, callers = writers(tmp_path)
    assert tables == {"mastering/store.py", "rogue.py"} and callers == {"rogue.py"}
