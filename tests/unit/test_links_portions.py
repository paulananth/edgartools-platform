"""The links are calculated in parts held on disk, and give what one whole calculation gives."""
import json

import pytest

from edgar_warehouse.mastering import links
from edgar_warehouse.silver_writer import writer

TYPES = {"OWNS": {"hierarchy": True, "ultimate_parent": "chain", "ultimate_type": "TOP"}, "TOP": {}, "ENDS": {"ends_parent_links": True},
         "ONE": {"one_parent": True}, "ISSUED": {"one_target": True}, "ADVISES": {}}


def test_the_types_that_read_each_others_links_share_one_part_and_every_other_link_follows_its_type_and_source():
    together = links._together(TYPES)
    assert together == {"OWNS", "TOP", "ENDS", "ONE"}
    assert {links.portion_of(kind, source, together) for kind in together for source in "abcdef"} == {links.TOGETHER}
    parts = {links.portion_of("ISSUED", f"s{n}", together) for n in range(500)}
    assert links.TOGETHER not in parts and len(parts) > 32 and max(parts) <= links.PORTIONS
    assert links.portion_of("ISSUED", "a", together) == links.portion_of("ISSUED", "a", together)


def record(subject, revision=1, links_=(), **other):
    return {"assertion_id": f"{subject}-{revision}", "subject": subject, "source_code": "invented", "record_key": subject,
            "publication_key": "p", "revision": revision, "effective_at": f"2026-0{revision}-01T00:00:00+00:00", "kind": "company",
            "fields": {"name": {"op": "value", "value": "x" * 50}}, "identifiers": {}, "profiles": [], "relationships": list(links_), **other}


def link(kind, target, source=None, **other):
    return {"type": kind, "target_subject": target, "scope": "", "valid_from": "2026-01-01T00:00:00+00:00",
            **({"source_subject": source} if source else {}), **other}


class Store:
    """Records in memory, with every subject but `waiting` bound to the master of its name (two subjects may share one)."""

    def __init__(self, records, same=None):
        self.records, self.same = records, same or {}

    def linked_records(self):
        return ((r["subject"], json.dumps(r, separators=(",", ":"))) for r in self.records)

    def bound(self, ends):
        return {end: self.same.get(end, f"m-{end}") for end in ends if end != "waiting"}

    def master_states(self, entities):
        return {entity: {"kind": "company", "status": "accepted", "profiles": []} for entity in entities}

    def commit(self):
        pass


def many():
    """Every case at once: revisions of one record, one link stated by two records, two subjects of one master, a hierarchy with a
    cycle, a succession that ends a parent link, two targets at once, a link that waits, and a type the policy does not have."""
    records = [record(f"a{n}", 1, [link("ADVISES", f"f{n % 7}"), link("ADVISES", "shared", source="house")]) for n in range(40)]
    records += [record("a1", 2, [link("ADVISES", "f1")]), record("twin", 1, [link("ADVISES", "f2")])]
    records += [record(f"c{n}", 1, [link("OWNS", f"c{n + 1}")]) for n in range(6)] + [record("c6", 1, [link("OWNS", "c0")])]
    records += [record(f"p{n}", 1, [link("OWNS", f"p{n + 1}")]) for n in range(4)]
    records += [record("p1-ends", 1, [link("ENDS", "p9", source="p1", valid_from="2026-03-01T00:00:00+00:00")])]
    records += [record("s1", 1, [link("ISSUED", "f1"), link("ISSUED", "f2")]), record("s2", 1, [link("ISSUED", "f1")])]
    records += [record("w", 1, [link("ADVISES", "waiting"), link("NEVER", "f1")])]
    return Store(records, {"twin": "m-a2"})


@pytest.fixture
def rules(monkeypatch):
    side = {"from": ["company"], "to": ["company"]}
    types = {"OWNS": {**side, "hierarchy": True, "cycles": "invalid"}, "ENDS": {**side, "ends_parent_links": True},
             "ISSUED": {**side, "one_target": True}, "ADVISES": side}
    monkeypatch.setattr(links.relationships, "types_of", lambda policy: types)


def test_parts_give_the_links_periods_evidence_and_waiting_counts_of_one_whole_calculation(rules, monkeypatch):
    parts = links.calculate(many(), {}, "2026-12-31T00:00:00+00:00", [])
    monkeypatch.setattr(links, "portion_of", lambda *a: 0)
    monkeypatch.setattr(links, "PORTIONS", 1)
    whole = links.calculate(many(), {}, "2026-12-31T00:00:00+00:00", [])
    assert parts == whole
    edges, waiting = parts
    by_type = {kind: sum(edge["type"] == kind for edge in edges) for kind in ("ADVISES", "OWNS", "ENDS", "ISSUED")}
    assert by_type == {"ADVISES": 41, "OWNS": 4, "ENDS": 1, "ISSUED": 1}
    assert waiting == {"conflicting_targets": 1, "hierarchy_cycle": 1, "unresolved_endpoint": 1, "unsupported_relationship": 1}
    (shared,) = [edge for edge in edges if edge["target_id"] == "m-shared"]
    assert len(shared["evidence"]) == 39  # a1's second revision no longer states it
    ended = [edge["periods"][0].get("ended_by") for edge in edges if edge["type"] == "OWNS" and "m-p1" in (edge["source_id"], edge["target_id"])]
    assert ended and all(ended)


def test_a_link_keeps_the_start_the_last_build_gave_it_in_whichever_part_it_is(rules):
    observed = lambda on: [record(f"a{n}", 1, [link("ADVISES", "f", valid_from=on, valid_from_basis="observed", valid_to=None,
                                                  properties={})]) for n in range(30)]
    first, _ = links.calculate(Store(observed("2026-02-01T00:00:00+00:00")), {}, "2026-12-31T00:00:00+00:00", [])
    rows = [{**row, "valid_to_basis": None} for row in links.rows_of(first)["relationship"]]
    later, _ = links.calculate(Store(observed("2026-05-01T00:00:00+00:00")), {}, "2026-12-31T00:00:00+00:00", rows)
    assert {period["valid_from"] for edge in later for period in edge["periods"]} == {"2026-02-01T00:00:00+00:00"} and len(later) == 30


def test_no_part_holds_the_whole_set_and_no_field_a_link_does_not_read(rules, monkeypatch):
    seen, real = [], links.relationships.project
    monkeypatch.setattr(links.relationships, "project", lambda claims, *a, **k: seen.append(claims) or real(claims, *a, **k))
    links.calculate(Store([record(f"a{n}", 1, [link("ADVISES", "f")]) for n in range(300)]), {}, "2026-12-31T00:00:00+00:00", [])
    assert sum(map(len, seen)) == 300 and max(map(len, seen)) < 30
    assert {name for claims in seen for claim in claims.values() for name in claim} == {"relationships", "assertion_id", "source_meta"}


def test_a_table_with_no_check_is_written_as_its_rows_arrive():
    taken = []

    class Sink:
        def spec(self, table):
            return {"columns": [{"name": "id"}]}

        def write(self, spec, rows):
            for row in rows:
                taken.append(("written", row["id"]))
            return {"rows": 2}

    def rows():
        for n in (1, 2):
            taken.append(("read", n))
            yield {"id": n}

    writer.land(Sink(), "t", rows())
    assert taken == [("read", 1), ("written", 1), ("read", 2), ("written", 2)]
