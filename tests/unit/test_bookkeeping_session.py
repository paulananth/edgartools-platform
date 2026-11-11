"""A worker pays for a Bookkeeping process and connection once: `serve` answers many commands, the worker's
Session reuses one child, and the run's immutable parts are checked once (a hosted store: 2 s a command)."""
import io
import json
import os
import sys

import pytest

from edgar_warehouse.bookkeeping.clean import cli, engine as engine_module
from edgar_warehouse.bookkeeping.clean.engine import Bookkeeping
from edgar_warehouse.workers import control


class Book:
    def __init__(self):
        self.seen = []

    def tasks(self, run_id, profile, limit):
        self.seen.append(("claim", run_id, profile, limit))
        return [{"unit": 1}]

    def renew(self, envelope):
        self.seen.append(("renew", envelope))
        return {**envelope, "renewed": True}


def serve(book, *requests):
    out = io.StringIO()
    cli.serve(book, [json.dumps(r) + "\n" for r in requests], out)
    return [json.loads(line) for line in out.getvalue().splitlines()]


def test_serve_answers_each_command_with_one_line_and_hands_a_document_to_renew():
    book = Book()
    replies = serve(book,
                    {"argv": ["claim", "r1", "--profile", "source.read", "--limit", "1"]},
                    {"argv": ["renew", "--envelope", "-"], "document": {"claim": "c"}})
    assert replies == [{"result": [{"unit": 1}]}, {"result": {"claim": "c", "renewed": True}}]
    assert book.seen[0] == ("claim", "r1", "source.read", 1)


@pytest.mark.parametrize("argv", [["runs"], ["finalize", "r1"], ["init", "--runtime-role", "x"], ["nonsense"]])
def test_serve_refuses_what_the_task_protocol_does_not_name(argv):
    [reply] = serve(Book(), {"argv": argv})
    assert "error" in reply and "result" not in reply


def test_a_failed_command_is_an_error_line_and_the_next_command_still_runs():
    class Broken(Book):
        def tasks(self, *a, **k):
            raise RuntimeError("(psycopg2.errors.RaiseException) Stale lease")
    replies = serve(Broken(), {"argv": ["claim", "r", "--profile", "p", "--limit", "1"]},
                    {"argv": ["renew", "--envelope", "-"], "document": {}})
    assert "Stale lease" in replies[0]["error"] and replies[1]["result"] == {"renewed": True}


ECHO = ("import sys, json, os\n"
        "for line in sys.stdin:\n"
        "    r = json.loads(line)\n"
        "    if r['argv'] == ['boom']:\n"
        "        print(json.dumps({'error': 'x\\n(psycopg2.errors.RaiseException) Stale lease\\nSQL here'}), flush=True)\n"
        "    elif r['argv'] == ['die']:\n"
        "        os._exit(1)\n"
        "    else:\n"
        "        print(json.dumps({'result': os.getpid()}), flush=True)\n")


def session():
    return control.Session([sys.executable, "-c", ECHO])


def test_ten_commands_use_one_child_process():
    s = session()
    try:
        assert len({s.ask(("claim",)) for _ in range(10)}) == 1
    finally:
        s.close()


def test_an_error_line_is_the_database_reason_and_a_dead_child_is_replaced():
    s = session()
    try:
        first = s.ask(("claim",))
        with pytest.raises(control.ControlError, match="Stale lease"):
            s.ask(("boom",))
        with pytest.raises(control.ControlError):
            s.ask(("die",))
        assert s.ask(("claim",)) != first  # a new child answered
    finally:
        s.close()


def test_the_immutable_parts_of_a_run_are_read_once_per_submission(monkeypatch):
    reads = []

    class Artifacts:
        def json(self, ref):
            reads.append(ref)
            return {"body": {}, "digest": "d", "kind": "k", "name": "n", "version": "v"} if ref == "rules" else {}

    monkeypatch.setattr(engine_module, "digest", lambda value: "d" if value == {} else "s")
    monkeypatch.setattr(engine_module, "validate", lambda body, target: {"steps": []})
    monkeypatch.setattr(engine_module, "worklist", lambda manifest, config: [{"step": "a", "key": "1"}])
    book = Bookkeeping.__new__(Bookkeeping)
    book.artifacts, book._frozen_static = Artifacts(), {}
    submission = {"rules": "rules", "inputs": "inputs", "kind": "k", "name": "n", "rule_version": "v",
                  "target": "t", "profiles": {}, "worklist_hash": "s", "scope": {}}

    first = book._static(submission)
    first[3].append({"step": "generated", "key": "2"})  # a run adds its generated work to its own copy
    second = book._static(submission)

    assert reads == ["rules", "inputs"]
    assert len(second[3]) == 1
