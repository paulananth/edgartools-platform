"""Run files the store decides (ticket 202): built by the loader on every load, never asked of the operator.

A target declares, per run file, a registered `method` with its `purpose` and `why` (`config.run_inputs`). The loader
calls `derive` for each such file the caller did not give, writes it beside the load and says what it made. The same
method gives the same answer on a go-live and on a daily run, from what the store holds then."""
from __future__ import annotations

import json
from pathlib import Path

from edgar_warehouse.mdm import waterfall

COMPANY_CODE = "sec.company.v1"


def lei_scope(store, **_) -> dict:
    """`{LEI: {selected: true}}`: every LEI the store holds on a record (as an identifier, or as the LEI an adviser
    states) and every LEI the waterfall pass paired with a company. A finder source masters only these."""
    found = {lei for (lei,) in store.rows("select distinct lei from mastering_record where lei is not null")}
    for (body,) in store.rows("select body from mastering_record where body like %s", ['%"adv_lei"%']):
        stated = (json.loads(body).get("cross_references") or {}).get("adv_lei")
        found.update(value for value in (stated if isinstance(stated, list) else [stated]) if isinstance(value, str) and value)
    found.update(value for (value,) in store.rows("select distinct value from mastering_name_key where role='cascade'"))
    return {lei: {"selected": True} for lei in sorted(found)}


def wanted_names(store, **_) -> list:
    """The name keys of the companies in the store, as the whole-publication reading keeps them."""
    return sorted(waterfall.wanted_names(waterfall.stored_filers(store, COMPANY_CODE)))


def none_flagged(store, **_) -> list:
    """An empty list: the run flags no value (a list the target reads only to flag, and nothing needs flagging)."""
    return []


METHODS = {"lei_scope": lei_scope, "wanted_names": wanted_names, "none_flagged": none_flagged}


def derive(method: str, name: str, *, folder: Path, store) -> tuple[Path, int]:
    """Write the run file `name` by `method` under `folder`: (its path, how many values it holds)."""
    if method not in METHODS:
        raise ValueError(f"No derivation named {method}: {sorted(METHODS)}")
    value = METHODS[method](store)
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{name}.json"
    path.write_text(json.dumps(value, sort_keys=True) + "\n")
    return path, len(value)
