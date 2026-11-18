"""silver.land's receipt counts the distinct keys of everything it landed and digests them. A set of every key grows with
the input; the keys go to disk in sorted runs instead, and the
receipt is byte for byte the one the set gave. Every key here is invented."""

import hashlib
import json
import random

from edgar_warehouse.silver_writer.keyset import KeySet, missing


def _old_digest(seen: set) -> str:
    return hashlib.sha256(json.dumps(sorted(seen), separators=(",", ":")).encode()).hexdigest()


def _keys(count: int, seed: int = 7) -> list[tuple[str, str]]:
    random.seed(seed)
    return [(f"acc-{random.randrange(count // 3 + 1):05d}", f"h{random.randrange(40)}") for _ in range(count)]


def test_the_distinct_count_and_sorted_keys_are_those_of_a_set_across_many_spills():
    keys = _keys(5000)
    with KeySet(limit=37) as held:
        for start in range(0, len(keys), 100):
            held.add(keys[start:start + 100])
        assert list(held.sorted()) == sorted(set(keys))
        assert held.summary()[0] == len(set(keys))


def test_the_digest_is_the_one_the_sorted_set_gave_so_stored_receipts_still_verify():
    keys = _keys(3000, seed=3)
    with KeySet(limit=50) as held:
        held.add(keys)
        assert held.summary() == (len(set(keys)), _old_digest(set(keys)))
    with KeySet(limit=50) as empty:
        assert empty.summary() == (0, _old_digest(set()))


def test_what_is_held_in_memory_never_passes_the_limit_and_the_spill_files_are_removed():
    with KeySet(limit=25) as held:
        for key in _keys(2000):
            held.add([key])
            assert len(held._buffer) <= 25
        folder = held._folder
        assert folder.exists() and len(list(folder.iterdir())) > 1  # spilled to sorted runs
    assert not folder.exists()


def test_missing_asks_silver_a_group_of_first_key_values_at_a_time_and_counts_what_it_lacks():
    wanted = sorted({("a1", "x"), ("a1", "y"), ("a2", "x"), ("a3", "x"), ("a3", "z"), ("a4", "x")})
    asked = []

    def fetch(values):
        asked.append(list(values))
        return {("a1", "x"), ("a1", "y"), ("a3", "x"), ("a4", "x")}  # silver lacks (a2, x) and (a3, z)

    assert missing(iter(wanted), fetch, group=2) == 2
    assert asked == [["a1", "a2"], ["a3", "a4"]]  # never more than the group's first-key values in one question
    assert missing(iter([]), fetch, group=2) == 0
