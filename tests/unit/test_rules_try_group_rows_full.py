"""Short words for group-and-attach-rows name their stored keys and refuse the rest."""
import copy
import json

from edgar_warehouse.control_contract import canonical
from edgar_warehouse.rules.bench_families.group_rows_full import explain, words
from edgar_warehouse.rules.source_engine import combine_tables

GROUP = {"source": "extra", "table": "names", "key": "id", "value": "alias", "mode": "list the values",
         "order_by": ["alias"], "distinct": True, "skip_null_values": True, "checks": {}, "where": {}}
SHORT = {"execution": {"profile": "source.combine"}, "combine": {
    "max_rows": 1000,
    "groups": {"aliases": GROUP},
    "tables": {"records": {"source": "primary", "table": "records", "checks": {}, "where": {},
                           "attach": {"aliases": {"group": "aliases", "key": "id",
                                                  "on_missing": "empty", "replace": False}}}},
}}
READINGS = {"primary": {"artifacts": [{"tables": {"records": [{"id": "R1"}]}}]},
            "extra": {"artifacts": [{"tables": {"names": [{"id": "R1", "alias": "B"},
                                                          {"id": "R1", "alias": "A"}]}}]}}
REDUCE = {"execution": {"profile": "source.combine"}, "reduce": {
    "max_rows": 100, "max_input_bytes": 1000, "max_state_bytes": 1000, "max_keys": 10, "max_members": 10,
    "max_output_rows": 10, "max_output_bytes": 1000,
    "groups": {"filed": {"source": "extra", "table": "names", "keys": ["id"], "mode": "how many rows",
                         "count": "n", "sample": None, "sample_limit": 0}}}}


def _short(mode=None, attach="attach", reduce=False):
    rule = copy.deepcopy(REDUCE if reduce else SHORT)
    if mode is not None and reduce:
        rule["reduce"]["groups"]["filed"]["mode"] = mode
    elif mode is not None:
        rule["combine"]["groups"]["aliases"]["mode"] = mode
    if not reduce and attach != "attach":
        rule["combine"]["tables"]["records"][attach] = rule["combine"]["tables"]["records"].pop("attach")
    return json.dumps(rule)


def test_the_r1_case_in_words_is_the_stored_plan_and_carries_both_aliases():
    shown = explain(_short())
    assert shown["lines"] == [{"word": "list the values", "stored": "collect"},
                              {"word": "attach", "stored": "joins"}]
    stored = shown["document"]["combine"]
    assert stored["groups"]["aliases"]["mode"] == "collect"
    assert list(stored["tables"]["records"]["joins"]) == ["aliases"]
    assert "attach" not in stored["tables"]["records"]
    assert combine_tables(stored, READINGS, canonical) == {"records": [{"id": "R1", "aliases": ["A", "B"]}]}


def test_each_group_word_is_replaced_by_its_stored_key():
    for word, stored in [("list the values", "collect"), ("one flat list", "collect_flat"),
                         ("first row", "first"), ("last row", "last"), ("exactly one row", "one")]:
        distinct = word in ("list the values", "one flat list")
        rule = json.loads(_short(mode=word))
        rule["combine"]["groups"]["aliases"]["distinct"] = distinct
        shown = explain(json.dumps(rule))
        assert shown["document"]["combine"]["groups"]["aliases"]["mode"] == stored, word
        assert shown["lines"][0] == {"word": word, "stored": stored}


def test_the_whole_set_words_are_replaced_in_a_reduction():
    for word, stored in [("how many rows", "count"), ("distinct values", "members"), ("most frequent", "most")]:
        rule = json.loads(_short(reduce=True))
        group = rule["reduce"]["groups"]["filed"]
        group["mode"] = word
        if stored != "count":
            group.update(member="id", sample="top")
        shown = explain(json.dumps(rule))
        assert shown["document"]["reduce"]["groups"]["filed"]["mode"] == stored, (word, shown)
        assert shown["lines"] == [{"word": word, "stored": stored}]


def test_how_many_at_this_path_is_refused_and_is_not_a_word():
    assert "how many at this path" not in [item["word"] for item in words]
    for rule in (_short(mode="how many at this path"), _short(mode="how many at this path", reduce=True)):
        refused = explain(rule)
        assert list(refused) == ["refused"]
        assert "Read the file" in refused["refused"] and "list the values" in refused["refused"]


def test_a_word_of_attach_a_source_record_is_refused():
    for word in ("same identifier", "how many that identifier allows", "create a master", "send to review"):
        refused = explain(_short(mode=word))
        assert list(refused) == ["refused"] and "Attach a source record" in refused["refused"], word
    keyed = json.loads(_short())
    keyed["combine"]["tables"]["records"]["send to review"] = {}
    assert "Attach a source record" in explain(json.dumps(keyed))["refused"]


def test_a_stored_key_typed_bare_is_refused_with_the_word_to_type():
    for key, word in [("collect", "list the values"), ("collect_flat", "one flat list"), ("first", "first row"),
                      ("last", "last row"), ("one", "exactly one row")]:
        refused = explain(_short(mode=key))
        assert list(refused) == ["refused"] and f"'{key}' is a stored key. Type '{word}' instead." in refused["refused"]
    joins = explain(_short(attach="joins"))
    assert "Type 'attach' instead" in joins["refused"]
    count = explain(_short(mode="count", reduce=True))
    assert "Type 'how many rows' instead" in count["refused"]


def test_a_word_in_the_other_kind_of_contract_is_refused():
    assert "reduction" in explain(_short(mode="how many rows"))["refused"]
    assert "combination" in explain(_short(mode="first row", reduce=True))["refused"]
    assert "'sideways'" in explain(_short(mode="sideways"))["refused"]


def test_a_bad_short_rule_or_a_document_the_engine_refuses_is_a_refusal():
    for rule in ["not json", "[1]", "{}", json.dumps({**SHORT, "reduce": REDUCE["reduce"]}),
                 json.dumps({"execution": SHORT["execution"], "combine": []})]:
        refused = explain(rule)
        assert list(refused) == ["refused"] and refused["refused"], rule
    wrong_group = json.loads(_short())
    wrong_group["combine"]["tables"]["records"]["attach"]["aliases"]["group"] = "nobody"
    assert list(explain(json.dumps(wrong_group))) == ["refused"]
    no_limits = json.loads(_short(reduce=True))
    del no_limits["reduce"]["max_rows"]
    assert list(explain(json.dumps(no_limits))) == ["refused"]
