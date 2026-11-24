"""A review is one row per (subject, reason): a command that proposes a subject twice is an error in the database."""

from __future__ import annotations

from types import SimpleNamespace

from edgar_warehouse.mastering.store import Postgres, Store


class Cursor:
    def __init__(self):
        self.commands = []

    def execute(self, text, values=()):
        self.commands.append((text, list(values)))


def test_two_waiting_records_of_one_subject_open_one_review_in_one_command():
    """A forced load stopped 10 of 16 openfigi bundles, each attempt, with "ON CONFLICT DO UPDATE command cannot affect row a second
    time": two waiting records of one subject in a batch proposed (subject, reason) twice. The last assertion wins, as it would one by one."""
    fake = SimpleNamespace(cursor=Cursor(), review_upsert=Postgres.review_upsert)
    Store.open_reviews(fake, "waiting", [("s1", "a1"), ("s2", "a2"), ("s1", "a3")])
    (text, values), = fake.cursor.commands
    assert text.count("(%s,%s,%s,1)") == 2 and values == ["s1", "waiting", "a3", "s2", "waiting", "a2"]
