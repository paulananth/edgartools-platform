"""One profiling run: inputs → findings.yaml + REPORT.md.

Every claim carries its evidence; anything without evidence is "unknown".
Samples of personal columns are masked to their shape.
"""

from __future__ import annotations

import datetime as dt
import shutil
import sys
import tempfile
import time
from pathlib import Path

import duckdb

from . import classify, codes, hierarchy, identifiers, inputs, keys, names, profile, quality, sensitivity, timing

VERSION = "data-profiling 1"
SILVER_INTEGER = "BIGINT"  # count-derived integers are never narrower (CLAUDE.md, schema conventions)
MB_PER_SECOND = 40  # records read by Python, for the time estimate before a long pass


_clock = [time.monotonic()]


def now() -> str:
    """The local business time (America/New_York), with its offset."""
    try:
        from zoneinfo import ZoneInfo
        return dt.datetime.now(ZoneInfo("America/New_York")).isoformat(timespec="seconds")
    except Exception:  # no time zone database: say so by keeping the UTC offset
        return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


def say(message: str) -> None:
    """Progress on stderr, with the seconds since the last message."""
    now = time.monotonic()
    print(f"[{now - _clock[0]:6.1f}s] {message}", file=sys.stderr, flush=True)
    _clock[0] = now


def profile_inputs(sources: dict[str, str], name: str, limit: int = inputs.DEFAULT_LIMIT,
                   sample: int = inputs.SAMPLE_RECORDS, seed: int = 0, kinds: tuple[str, ...] = (),
                   work: Path | None = None) -> dict:
    """Profile every input and return the findings (the findings.yaml document)."""
    started = time.monotonic()
    work = work or Path(tempfile.mkdtemp(prefix="profiling-"))
    work.mkdir(parents=True, exist_ok=True)
    database = work / "profile.duckdb"
    database.unlink(missing_ok=True)
    con = duckdb.connect(str(database))  # parts are tables on disk, not in memory
    parts: dict[str, inputs.Part] = {}
    for input_name, location in sources.items():
        if not location.startswith("env:"):
            path = Path(location).expanduser()
            size = inputs.size_of(path) if inputs.format_of(path) not in {"sqlite", "duckdb"} else path.stat().st_size
            if size > limit:
                say(f"{input_name}: {size / inputs.GB:.1f} GB is over the {limit / inputs.GB:.0f} GB limit: "
                    f"sampling {sample} records (seed {seed}), then full passes for key candidates; "
                    f"about {2 * size / (MB_PER_SECOND * 1024 ** 2) / 60:.0f} minutes per pass")
        registered = inputs.register(con, input_name, location, work / input_name, limit, sample, seed)
        sha = inputs.digest(Path(location).expanduser()) if not location.startswith("env:") else None
        for part in registered:
            part.sha256 = sha if part.parent is None else None
            parts[part.name] = part
    say(f"registered {len(parts)} parts")

    profiles = {p: profile.columns(con, p) for p in parts}
    say("profiled columns")
    # A list of plain values has no key of its own: its parent's key and the place in the list.
    unique = {p: [] if keys.plain_values(cols) else keys.unique_keys(con, p, cols) for p, cols in profiles.items()}
    say("found unique keys")
    confirmed = {}
    for p, part in parts.items():
        if part.scan == "sampled" and part.parent is None:  # children keep keys found in the sample
            say(f"{p}: full pass for its identifier-like key candidates")
            confirmed[p] = keys.confirm_sampled(con, part, unique[p], profiles[p])
            say(f"{p}: confirmed {[c for c, e in confirmed[p].items() if e['unique']]} in full")
            # Only keys a full pass confirmed: a combination unique in a sample is not a key.
            unique[p] = [k for k in unique[p] if len(k) == 1 and confirmed[p].get(k[0], {}).get("unique")]
    found_links = keys.links(con, profiles, unique, parts, confirmed) + keys.composite_links(con, profiles, unique)
    child = keys.child_links(parts)
    say(f"found {len(found_links)} links")

    record_keys: dict[str, dict] = {}
    for p in sorted(parts, key=lambda n: n.count(".")):  # parents before their children
        parent = parts[p].parent
        parent_key = record_keys[parent]["columns"] if parent else None
        within = keys.unique_within_parent(con, p, profiles[p]) if parent and not unique[p] else None
        name = None
        if not parent and not unique[p]:
            people = sensitivity.person_part([c["name"] for c in profiles[p] if not c["structure"]])
            personal = {c["name"] for c in profiles[p]
                        if sensitivity.tag(c["name"], [], people)["sensitivity"] != "none"}
            name = names.name_basis(con, p, profiles[p], personal)
        record_keys[p] = keys.choose_record_key(p, unique[p], profiles[p], found_links, parent_key, within, name)

    findings_parts = [_part(con, p, parts, profiles, record_keys[p], found_links, kinds, confirmed.get(p, {}))
                      for p in parts]
    say("classified parts")
    _inherit(findings_parts, parts)
    by_name = {f["part"]: f for f in findings_parts}
    hierarchies = _hierarchies(con, by_name, profiles, found_links)
    say(f"found {len(hierarchies)} hierarchies")
    relationships = _relationships(found_links + child, by_name)
    _mask_samples(hierarchies, by_name)
    marked = _mark(hierarchies, by_name)
    _propose_kinds(findings_parts)
    for f in findings_parts:
        f["store_suggestion"] = classify.store(f["class"])
        f["silver"] = _silver(f, relationships) if f["class"] in {"transaction", "reference"} else None
    con.close()
    return {
        "version": 1,
        "dataset": {"name": name,
                    "inputs": [parts[p].finding(_rows(profiles, p)) for p in parts if parts[p].parent is None],
                    "scan": {"mode": "sampled" if any(x.scan == "sampled" for x in parts.values()) else "full",
                             "reason": f"an input over {limit / inputs.GB:.0f} GB" if any(
                                 x.scan == "sampled" for x in parts.values()) else None,
                             "seed": seed, "elapsed_seconds": round(time.monotonic() - started, 1)},
                    "profiled_at": now(),
                    "profiled_by": VERSION},
        "parts": findings_parts,
        "relationships": relationships,
        "hierarchies": hierarchies,
        "questions": _questions(findings_parts),
        "marked_rows": marked,  # written beside findings.yaml as invalid_rows.jsonl, never inside it
        "approval": {"status": "draft", "approved_by": None, "approved_words": None, "approved_at": None},
    }


def _part(con, p, parts, profiles, record_key, found_links, kinds, confirmed) -> dict:
    columns = profiles[p]
    names = [c["name"] for c in columns if not c["structure"]]
    people = sensitivity.person_part(names)
    tags = {c["name"]: sensitivity.tag(c["name"], _values(con, p, c), people) for c in columns if not c["structure"]}
    personal = {n for n, t in tags.items() if t["sensitivity"] != "none"}
    identity = {n for n in personal if set(sensitivity.words(n)) & sensitivity.IDENTITY}
    code_list = codes.code_lists(con, p, columns, record_key["columns"], identity)
    code_columns = {c["column"] for c in code_list} | {c["label_column"] for c in code_list if c["label_column"]}
    labelled = {c["column"] for c in code_list if c["label_column"]}
    key_labels = {c["label_column"] for c in code_list if c["label_column"] and [c["column"]] == record_key["columns"]}
    times = timing.roles(con, p, columns, record_key["columns"], personal)
    out = [l for l in found_links if l["from"]["part"] == p and l["to"]["part"] != p]
    inbound = [l for l in found_links if l["to"]["part"] == p and l["from"]["part"] != p]
    linked_columns = {c for l in out for c in l["from"]["columns"]}
    # A number with a label column is a code; any other number may be a measure, even with few values.
    measures = [c for c in columns if profile.is_numeric(c) and not c["structure"] and c["name"] not in linked_columns
                and c["name"] not in record_key["columns"] and c["name"] not in labelled]
    column_findings, identifier_findings = [], []
    for c in columns:
        if c["structure"]:
            continue
        tagged = tags[c["name"]]
        role = _role(c, record_key, linked_columns, code_columns, times, measures)
        top = [{"value": sensitivity.mask(t["value"]) if tagged["sensitivity"] != "none" else t["value"],
                "rows": t["rows"]} for t in c["top"]]
        column_findings.append({
            "name": c["name"], "type": profile.logical_type(c), "stored_type": c["type"], "fill": c["fill"], "distinct": c["distinct"], "unique": c["unique"],
            "shape": sensitivity.mask(c["shape"]) if c["shape"] else None, "shape_share": c["shape_share"],
            "top": top, "role": role, "sensitivity": tagged["sensitivity"], "sensitivity_signals": tagged["signals"]})
        if identifiers.identifier_shaped(c) or c["name"] in record_key["columns"]:
            identifier_findings.append(_identifier(con, p, c, record_key))
    parent = parts[p].parent
    facts = {
        "rows": columns[0]["rows"] if columns else 0, "key": record_key["columns"], "key_found": record_key["found"],
        "in_degree": len({l["from"]["part"] for l in inbound}),
        "out_degree": len({l["to"]["part"] for l in out}) + (1 if parent else 0),
        "self_ends": len({l["to"]["part"] for l in out}) == 1 and len(out) >= 2,
        "key_links": sum(1 for c in record_key["columns"] if c in linked_columns),
        "key_other": sum(1 for c in record_key["columns"] if c not in linked_columns),
        # The key's own label names an entity; other labels name codes.
        "name_like": sum(codes.name_like(c, code_columns - key_labels) for c in columns),
        # A column holding one value for every row describes nothing: not an attribute.
        "attributes": sum(1 for c in columns if not c["structure"] and c["name"] not in record_key["columns"]
                          and c["name"] not in code_columns and c["name"] not in linked_columns
                          and not profile.is_temporal(c) and c["distinct"] > 1),
        "labels": sum(1 for c in code_list if c["label_column"]),
        "measures": len(measures), "event_time": times["event_time"],
        "metadata_share": round(sum(bool(set(sensitivity.words(n)) & classify.METADATA_WORDS) for n in names)
                                / len(names), 3) if names else 0.0,
        "rows_pointing": max([_rows(profiles, l["from"]["part"]) for l in inbound] or [0]),
        "rows_pointed": max([_rows(profiles, l["to"]["part"]) for l in out] or [0]),
    }
    if not facts["in_degree"]:
        facts["rows_pointing"] = facts["rows"] - 1  # nothing points at it: "smaller than" cannot pass
    decided = classify.classify(facts)
    if decided["class"] not in {"transaction", "unknown"}:
        times["event_time"] = None  # an event time belongs to events
    kind = next((k for k in kinds if k.lower() == p.rsplit(".", 1)[-1].lower()), None)
    return {
        "part": p, "parent_part": parent, "rows": facts["rows"], "scan": parts[p].scan,
        "class": decided["class"], "confidence": decided["confidence"], "tests": decided["tests"],
        "runner_up": decided["runner_up"],
        "kind": kind,
        "proposed_kind": None,
        "record_key": {**{k: v for k, v in record_key.items() if k != "evidence_extra"}, "evidence": {
            **record_key.get("evidence_extra", {}),
            "unique": record_key["found"],
            "null_rows": max([c["rows"] - c["non_null"] for c in columns if c["name"] in record_key["columns"]] or [0]),
            "persistence": None,  # needs a second delivery: measured by compare
            **({"full_pass": confirmed} if confirmed else {})}},
        "identifiers": [i for i in identifier_findings if i],
        "columns": column_findings,
        "code_lists": code_list,
        "time": times,
        "quality": quality.find(quality.Facts(
            con=con, part=p, columns=[c for c in columns if not c["structure"]],
            roles={f["name"]: f["role"] for f in column_findings}, personal=personal, key=record_key["columns"],
            links=out, identifiers=[i for i in identifier_findings if i], code_lists=code_list))
        + quality.no_natural_key(record_key),
    }


def _values(con, p: str, c: dict) -> list[str]:
    """Up to 200 distinct values of a text column, for the value detectors (never written out)."""
    if not c["non_null"] or not profile.is_text(c):
        return []
    return [r[0] for r in con.execute(f"SELECT DISTINCT CAST({inputs.sql_name(c['name'])} AS VARCHAR) FROM "
                                      f"{inputs.sql_name(p)} WHERE {inputs.sql_name(c['name'])} IS NOT NULL "
                                      "LIMIT 200").fetchall()]


def _rows(profiles, part):
    return profiles[part][0]["rows"] if profiles[part] else 0


def _role(c, record_key, linked, code_columns, times, measures) -> str:
    if c["name"] in record_key["columns"]:
        return "key"
    if c["name"] in linked:
        return "link"
    if c["name"] in code_columns:
        return "code"
    if c["name"] in {times["as_of"]["from"], times["as_of"]["to"], times["as_at"], times["event_time"]} or \
            profile.is_temporal(c):
        return "date"
    if c in measures:
        return "measure"
    if identifiers.identifier_shaped(c):
        return "identifier"
    if profile.is_text(c) and c["distinct"] > 50:
        return "name" if c.get("tokens", 0) <= 6 else "text"
    return "other"


def _identifier(con, p, c, record_key) -> dict | None:
    values = [r[0] for r in con.execute(f"SELECT DISTINCT CAST({inputs.sql_name(c['name'])} AS VARCHAR) FROM "
                                        f"{inputs.sql_name(p)} WHERE {inputs.sql_name(c['name'])} IS NOT NULL").fetchall()]
    checked = identifiers.check_digits(values)
    dense = profile.is_integer(c) and identifiers.dense_sequence(c)
    is_key = c["name"] in record_key["columns"]
    if is_key:
        proposal, why = "record_key", "the part's record key"
    elif checked["family"]:
        proposal, why = "cross_reference", f"one shape and a {checked['family']} check digit: an issued identifier"
    elif c["unique"] >= 0.99 and not dense:
        proposal, why = "cross_reference", "one shape and unique: a second identifier for lookup only"
    else:
        proposal, why = "none", "repeats or is a local counter"
    return {"column": c["name"], "shape": sensitivity.mask(c["shape"]) if c["shape"] else None,
            "check_digit": checked["family"], "pass_rate": checked["pass_rate"], "chance_rate": checked["chance_rate"],
            "fill": c["fill"], "unique": c["unique"], "local_counter": dense, "proposal": proposal, "why": why}


def _inherit(found: list[dict], parts) -> None:
    """A list inside a record that its own tests do not class (no key of its own, or "unknown")
    is an attribute list of its parent: same class."""
    by_name = {f["part"]: f for f in found}
    for f in sorted(found, key=lambda x: x["part"].count(".")):
        parent = f["parent_part"]
        if parent and (not f["record_key"]["found"] or f["class"] == "unknown") \
                and by_name[parent]["class"] != "unknown":
            f["class"] = by_name[parent]["class"]
            f["confidence"] = by_name[parent]["confidence"]
            f["tests"] = [{"class": f["class"], "test": "a list inside its parent's records, with no key of its own",
                           "value": parent, "passed": True}]


def _hierarchies(con, parts: dict, profiles, links) -> list[dict]:
    found = []
    parent_columns = {(l["from"]["part"], l["from"]["columns"][0]) for l in links
                      if l["from"]["part"] == l["to"]["part"] and len(l["from"]["columns"]) == 1}
    for p, f in parts.items():
        listed = {x["column"] for x in f["code_lists"]} | {x["label_column"] for x in f["code_lists"]}
        # A parent column is its own hierarchy (below); here only code columns that are not one.
        key = f["record_key"]["columns"]
        key_side = set(key) | {x["label_column"] for x in f["code_lists"] if [x["column"]] == key}
        code_columns = [c for c in profiles[p] if c["name"] in listed and (p, c["name"]) not in parent_columns
                        and (f["class"] == "reference" or c["name"] not in key_side)]
        for h in hierarchy.by_dependency(con, p, code_columns, key):
            h["type"] = "reference"
            found.append(h)
    for link in links:
        a, b = link["from"], link["to"]
        if a["part"] == b["part"] and len(a["columns"]) == 1:
            h = hierarchy.by_parent_column(con, a["part"], a["columns"][0], b["columns"][0],
                                           parts[a["part"]]["record_key"]["columns"])
            h["type"] = "reference" if parts[a["part"]]["class"] == "reference" else "master_data"
            found.append(h)
    for p, f in parts.items():
        ends = [l for l in links if l["from"]["part"] == p and l["to"]["part"] != p]
        targets = {l["to"]["part"] for l in ends}
        if f["class"] == "relationship" and len(ends) == 2 and len(targets) == 1:
            role = _role_column(f)
            child, parent = _child_first(ends, f["record_key"]["columns"])
            for h in hierarchy.by_link_part(con, p, child, parent, role, f["record_key"]["columns"]):
                h["type"] = "master_data"
                found.append(h)
    return found


def _child_first(ends: list[dict], key: list[str]) -> tuple[str, str]:
    """A link part's two end columns, child first: the end in the record key has one row per role."""
    a, b = (e["from"]["columns"][0] for e in ends)
    return (b, a) if b in key and a not in key else (a, b)


def _role_column(f: dict) -> str | None:
    """A link part's role: a code column in its key, else any code column that is not a link."""
    linked = {c["name"] for c in f["columns"] if c["role"] == "link"}
    listed = [x["column"] for x in f["code_lists"] if x["column"] not in linked]
    return next((c for c in f["record_key"]["columns"] if c in listed), listed[0] if listed else None)


def _relationships(links, parts: dict) -> list[dict]:
    found = []
    for link in links:
        a, b = parts[link["from"]["part"]], parts[link["to"]["part"]]
        together = (a["class"] == "relationship" and b["class"] == "master") or \
                   (a["parent_part"] == b["part"] and a["class"] == b["class"] == "master")
        why = ("a link between masters, mastered with them" if a["class"] == "relationship" else
               "an attribute list of its master" if together else
               f"a {a['class']} part pointing at a {b['class']} part: onboarded after it")
        found.append({
            "relationship": f"{link['from']['part']}.{'+'.join(link['from']['columns'])} → "
                            f"{link['to']['part']}.{'+'.join(link['to']['columns'])}",
            "from": link["from"], "to": link["to"], "inclusion": link["inclusion"],
            "cardinality": link["cardinality"], "via_part": a["part"] if a["class"] == "relationship" else None,
            "role_column": _role_column(a) if a["class"] == "relationship" else None,
            "valid": {"from": a["time"]["as_of"]["from"], "to": a["time"]["as_of"]["to"]},
            "onboard": "together" if together else "separate", "why": why, "evidence": link["evidence"]})
    return found


def _silver(f: dict, relationships: list[dict]) -> dict:
    links = [r for r in relationships if r["from"]["part"] == f["part"]]
    return {
        "table": f["part"].replace(".", "_").lower(),
        "grain": f"one row per {' + '.join(f['record_key']['columns'])}",
        "columns": [{"name": c["name"], "type": SILVER_INTEGER if c["type"] in profile.INTEGERS else c["type"],
                     "nullable": c["fill"] < 1.0, "definition": None,
                     "source": f"{f['part']}.{c['name']}", "sensitivity": c["sensitivity"]} for c in f["columns"]],
        "key": f["record_key"]["columns"],
        "links": [{"columns": r["from"]["columns"], "kind": None, "to_part": r["to"]["part"],
                   "source_key": r["from"]["columns"][0], "mdm_id_column": f"{r['from']['columns'][0]}_mdm_id",
                   "inclusion": r["inclusion"]} for r in links],
        "time": {"as_of": f["time"]["as_of"]["from"], "as_at": f["time"]["as_at"] or "loaded_at",
                 "event_time": f["time"]["event_time"]},
        "partition": [f["time"]["event_time"]] if f["time"]["event_time"] else [],
        "load_mode": "append" if f["class"] == "transaction" else "snapshot",
        "why": "events are appended and never changed" if f["class"] == "transaction"
        else "a published code-set version replaces the previous one",
    }


def _mask_samples(hierarchies: list[dict], parts: dict) -> None:
    """Hierarchy samples and role values of a personal column keep their shape only."""
    for h in hierarchies:
        tags = {c["name"]: c["sensitivity"] for c in parts[h["part"]]["columns"]}
        for level in h["levels"]:
            if tags.get(level["column"], "none") != "none":
                level["samples"] = [sensitivity.mask(v) for v in level["samples"]]
        role_column = _role_column(parts[h["part"]])
        if h.get("role") and tags.get(role_column, "none") != "none":
            h["role"] = sensitivity.mask(h["role"])
            h["hierarchy"] = f"{h['part']}: per role (masked)"


def _mark(hierarchies: list[dict], parts: dict) -> list[dict]:
    """Each hierarchy's invalid rows, masked where a column is personal, with the evidence for each fix
    written from the masked values; the hierarchy's part gets one quality item."""
    marked = []
    for h in hierarchies:
        rows = h.pop("marked")
        personal = {c["name"] for c in parts[h["part"]]["columns"] if c["sensitivity"] != "none"}

        def shown(column, value):
            return sensitivity.mask(value) if column in personal and value is not None else value

        for m in rows:
            m["hierarchy"] = h["hierarchy"]  # the role in its name is masked when personal
            m["key"] = {k: shown(k, v) for k, v in m["key"].items()}
            m["value"], m["fix"] = shown(m["column"], m["value"]), shown(m["parent_column"], m["fix"])
            support = m.pop("support")
            if support:
                m["fix_evidence"] = (f"{support['rows']} of {support['of']} rows with {m['column']} {m['value']} "
                                     f"have {m['parent_column']} {m['fix']}")
        parts[h["part"]]["quality"] += quality.hierarchy_items(h, rows)
        marked += rows
    return marked


def _propose_kinds(parts: list[dict]) -> None:
    """A master part with no existing kind gets a proposed domain and kind, for approval."""
    for f in parts:
        if f["class"] == "master" and not f["kind"] and not f["parent_part"]:
            name = f["part"].rsplit(".", 1)[-1]
            f["proposed_kind"] = {"domain": name, "kind": name,
                                  "why": "; ".join(t["test"] for t in f["tests"] if t["passed"])}


def _questions(parts: list[dict]) -> list[dict]:
    asked = []
    for f in parts:
        if f["proposed_kind"]:
            asked.append({"id": f"q{len(asked) + 1}", "about": f["part"],
                          "question": f"Is {f['part']} a new master kind named '{f['proposed_kind']['kind']}'?",
                          "recommendation": f"yes: {f['proposed_kind']['why']}", "answer": None})
        if not f["record_key"]["found"] and not f["parent_part"]:
            asked.append({"id": f"q{len(asked) + 1}", "about": f["part"],
                          "question": f"{f['part']} has no unique column: use the designed key?",
                          "recommendation": f["record_key"]["rule"], "answer": None})
        if f["class"] == "unknown":
            asked.append({"id": f"q{len(asked) + 1}", "about": f["part"],
                          "question": f"Which class is {f['part']}? Its tests did not decide.",
                          "recommendation": "keep it raw (bronze only) until decided", "answer": None})
    return asked
