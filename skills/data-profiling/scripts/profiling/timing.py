"""Time roles of a part: valid time ("as of"), record time ("as at"), event time, series.

Words in column names are generic (start, end, updated, ...); a role also
needs the values to agree (start ≤ end in ≥ 99% of rows, one modal step for a
series).
"""

from __future__ import annotations

from .inputs import sql_name
from .profile import is_numeric, is_temporal
from .sensitivity import words

START = {"start", "from", "begin", "begins", "open", "opened", "effective", "valid", "since", "initial"}
END = {"end", "to", "until", "close", "closed", "expiry", "expires", "expiration", "thru", "through", "next"}
RECORDED = {"updated", "update", "modified", "recorded", "loaded", "changed", "last", "ingested", "captured"}
STEPS = 0.9


def _as_time(column: str) -> str:
    return f"TRY_CAST({sql_name(column)} AS TIMESTAMP)"


def valid_pair(con, part: str, temporal: list[dict]) -> dict | None:
    """Two date columns named as a start and an end, with start ≤ end in ≥ 99% of rows."""
    for s in temporal:
        for e in temporal:
            if s is e or not set(words(s["name"])) & START or not set(words(e["name"])) & END:
                continue
            ordered, both = con.execute(
                f"SELECT count(*) FILTER (WHERE {_as_time(s['name'])} <= {_as_time(e['name'])}), "
                f"count(*) FILTER (WHERE {_as_time(s['name'])} IS NOT NULL AND {_as_time(e['name'])} IS NOT NULL) "
                f"FROM {sql_name(part)}").fetchone()
            if both and ordered / both >= 0.99:
                return {"from": s["name"], "to": e["name"], "ordered": round(ordered / both, 6)}
    return None


def roles(con, part: str, columns: list[dict], key: list[str], personal: set[str] = frozenset()) -> dict:
    """Time roles; a personal date (a birth date) is an attribute, never an event time."""
    temporal = [c for c in columns if is_temporal(c) and not c["structure"]]
    pair = valid_pair(con, part, temporal)
    in_pair = {pair["from"], pair["to"]} if pair else set()
    recorded = next((c["name"] for c in temporal if set(words(c["name"])) & RECORDED and c["name"] not in in_pair), None)
    others = [c for c in temporal if c["name"] not in in_pair and c["name"] != recorded and c["name"] not in personal]
    event = others[0]["name"] if others else None
    return {"delivery": "unknown",
            "as_of": {"from": pair["from"] if pair else None, "to": pair["to"] if pair else None},
            "as_at": recorded, "event_time": event,
            "versions_per_key": versions(con, part, key, [recorded, pair["from"] if pair else None, event]),
            "series": series(con, part, columns, key, temporal), "refresh": "unknown"}


def versions(con, part: str, key: list[str], times: list[str | None]) -> dict | None:
    """Rows per business key when the record key holds a time column (a key and the time it was recorded
    or became valid): the middle and the 99th percentile. None when the key has no time column."""
    stamp = next((t for t in times if t and t in key), None)
    entity = [k for k in key if k != stamp]
    if not stamp or not entity:
        return None
    group = ", ".join(map(sql_name, entity))
    p50, p99 = con.execute(f"SELECT quantile_disc(n, 0.5), quantile_disc(n, 0.99) FROM "
                           f"(SELECT count(*) n FROM {sql_name(part)} GROUP BY {group})").fetchone()
    return {"p50": int(p50), "p99": int(p99)} if p50 is not None else None


SAMPLE_PREFIX = "0"  # keys whose sha256 starts with this: about 1 in 16, the same keys in every delivery
SAMPLE_CAP = 4096  # a part with at most this many rows has every key sampled


def fingerprint(con, part: str, key: list[str], columns: list[dict], latest: str | None) -> dict:
    """A small, repeatable sample of the part's keys as sha256 hashes, each with the sha256 of its row
    (`columns`: the ones to hash, personal columns left out by the caller): two deliveries' samples hold
    the same keys, so compare measures persistence, changes and the delivery kind from hashes only.
    Never written for a key holding personal values, nor for a part read as a sample (the caller decides).
    A number is hashed by its value (1 and 1.0 alike), so a type read differently changes nothing."""
    def text(c: dict) -> str:
        value = f"CAST({sql_name(c['name'])} AS DOUBLE)" if is_numeric(c) else sql_name(c["name"])
        return f"coalesce(CAST({value} AS VARCHAR), '')"
    by_name = {c["name"]: c for c in columns}
    joined = lambda cols: "concat_ws(chr(31), " + ", ".join(text(c) for c in cols) + ")"
    size = con.execute(f"SELECT count(*) FROM {sql_name(part)}").fetchone()[0]
    prefix = "" if size <= SAMPLE_CAP else SAMPLE_PREFIX
    rows = con.execute(f"""SELECT "__key_hash", "__row_hash" FROM (
        SELECT sha256({joined([by_name[k] for k in key])}) "__key_hash",
               sha256({joined(columns)}) "__row_hash" FROM {sql_name(part)})
        WHERE starts_with("__key_hash", '{prefix}') ORDER BY 1 LIMIT {SAMPLE_CAP}""").fetchall()
    newest = con.execute(f"SELECT CAST(max(TRY_CAST({sql_name(latest)} AS TIMESTAMP)) AS VARCHAR) "
                         f"FROM {sql_name(part)}").fetchone()[0] if latest else None
    return {"prefix": prefix, "keys": dict(rows), "capped": len(rows) == SAMPLE_CAP and size > SAMPLE_CAP,
            "latest": newest, "latest_column": latest}


def series(con, part: str, columns: list[dict], key: list[str], temporal: list[dict]) -> dict | None:
    """(entity key, time) unique, a numeric measure, and one modal step between times for ≥ 90% of steps."""
    times = [c["name"] for c in temporal if c["name"] in key]
    measures = [c for c in columns if is_numeric(c) and not c["structure"] and c["name"] not in key]
    if len(times) != 1 or not measures:
        return None
    entity = [c for c in key if c != times[0]]
    group = ", ".join(map(sql_name, entity)) if entity else "1"
    t = _as_time(times[0])
    step, share, gaps = con.execute(f"""
        WITH s AS (SELECT {t} - lag({t}) OVER (PARTITION BY {group} ORDER BY {t}) d FROM {sql_name(part)}),
             m AS (SELECT d, count(*) n FROM s WHERE d IS NOT NULL GROUP BY d ORDER BY n DESC LIMIT 1)
        SELECT CAST(m.d AS VARCHAR), m.n / (SELECT count(*) FROM s WHERE d IS NOT NULL),
               (SELECT count(*) FROM s WHERE d > m.d) FROM m""").fetchone() or (None, 0, 0)
    if step is None or share < STEPS:
        return None
    return {"key": entity, "time": times[0], "step": step, "step_share": round(float(share), 6), "gaps": gaps}
