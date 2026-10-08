"""SEC's place-code table as `{code: {place, type, iso}}`, rebuilt from the
published RDM version the Mastering Policy pins (`sec-place-codes` 1). The
YAML it was imported from is removed (profiling ticket 02); this is the same
map, code for code (tests/mdm/test_sec_place_codes.py)."""

from edgar_warehouse.rules import files


def table() -> dict[str, dict]:
    rebuilt = {}
    for row in files.pinned_reference("sec-place-codes"):
        targets = {(x[0], x[3]): x[2] for x in row["crosswalk"]}
        rebuilt[row["code"]] = {"place": row["label"], "type": targets[("sec-place-types", "broad")],
                                "iso": targets.get(("iso-3166", "exact"))}
    return rebuilt
