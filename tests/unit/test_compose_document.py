"""A composed input is its slots' receipts filled into a document. The filling is one pure function, so the
engine (receipts from the database) and a local runner (receipts held in memory) cannot drift apart."""
from edgar_warehouse.bookkeeping.clean.compose import compose_document


def test_slots_are_filled_with_receipts_and_a_nested_compose_is_placed_as_its_own_document():
    placed = []

    def place(document):
        placed.append(document)
        return {"placed": len(placed)}

    def receipt_of(dependency):
        return {"uri": f"file:///{dependency['step']}/{dependency['key']}"}

    body = {"slots": {"main": {"step": "read", "key": "a"},
                      "many": [{"step": "read", "key": "b"}, {"step": "read", "key": "c"}],
                      "inner": {"compose": {"slots": {"x": {"step": "read", "key": "d"}},
                                            "document": {"x": {"slot": "x"}}}}},
            "document": {"main": {"slot": "main"}, "list": [{"slot": "many"}], "inner": {"slot": "inner"},
                         "note": "kept as written"}}

    result = compose_document(body, receipt_of, place)

    assert placed[0] == {"x": {"uri": "file:///read/d"}}  # the nested document is placed first
    assert placed[1] == {"main": {"uri": "file:///read/a"},
                         "list": [[{"uri": "file:///read/b"}, {"uri": "file:///read/c"}]],
                         "inner": {"placed": 1}, "note": "kept as written"}
    assert result == {"placed": 2}
