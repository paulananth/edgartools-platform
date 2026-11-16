"""Records stored before their golden record existed follow it in one statement a block, never one a row: each
statement is a round trip on a hosted store, and such a batch has an older row for every record."""
from edgar_warehouse.mastering.store import BLOCK, Store


class Cursor:
    def __init__(self, stored):
        self.stored, self.statements, self.answer = stored, [], []

    def execute(self, sql, values=()):
        self.statements.append((sql, list(values)))
        asked = set(values)
        self.answer = ([row for row in self.stored if row[1] in asked]
                       if sql.startswith("select assertion_id,subject,entity_id") else [])

    def executemany(self, sql, rows):
        for row in rows:  # what a driver does: one statement a row
            self.execute(sql, row)

    def fetchall(self):
        return self.answer


class Connection:
    def __init__(self, stored):
        self.made = Cursor(stored)

    def cursor(self):
        return self.made


def saved(count):
    stored = [(f"old-{n}", f"subject-{n}", None) for n in range(count)]
    store = Store(Connection(stored))
    store.staged = []
    store.save_records({f"subject-{n}": f"golden-{n}" for n in range(count)})
    return [(sql, values) for sql, values in store.cursor.statements if sql.startswith("update mastering_record")]


def test_a_thousand_older_records_follow_their_golden_records_in_one_statement():
    updates = saved(1000)

    assert len(updates) == 1
    sql, values = updates[0]
    assert values[:4] == ["old-0", "golden-0", "old-1", "golden-1"]   # each record with its own golden record
    assert values[-1000:] == [f"old-{n}" for n in range(1000)]        # and only those records are written
    assert "coalesce(bound_id,case assertion_id" in sql and "entity_id=case assertion_id" in sql


def test_more_records_than_a_block_take_one_statement_a_block():
    assert len(saved(BLOCK + 1)) == 2


def test_a_batch_with_no_older_record_writes_none():
    store = Store(Connection([]))
    store.staged = []
    store.save_records({"subject-0": "golden-0"})

    assert [sql for sql, _ in store.cursor.statements if sql.startswith("update")] == []
