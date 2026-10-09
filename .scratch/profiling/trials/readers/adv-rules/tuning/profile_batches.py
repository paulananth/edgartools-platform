"""Ticket 07 tuning: where does each Merge Stage batch spend its time?

Same setup as ../proving_run.py (all advisers, filings only, months in order),
for the first N batches. Each SQL statement is timed through SQLAlchemy's
cursor events; the report lists, per batch, SQL time vs the rest, and the
statements whose time grows most between the first and last batch.

    uv run --no-sync --extra mdm --with pgserver python <this> <rules> <readings> <batches>
"""
from __future__ import annotations

import importlib.util
import json
import re
import sys
import tempfile
import time
from collections import defaultdict
from pathlib import Path
from uuid import uuid4

from sqlalchemy import create_engine, event, text

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("proving_run", HERE.parent / "proving_run.py")
pr = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pr)


import os
EXPLAIN_MS = os.environ.get("EXPLAIN_MS")


def shape(sql: str) -> str:
    return re.sub(r"\s+", " ", sql).strip()[:160]


def main(root: Path, readings: Path, batches: int) -> None:
    filings, _ = pr.cohort(readings, 0)
    import pgserver
    server = pgserver.get_server(tempfile.mkdtemp(prefix="adv-tuning-"), cleanup_mode="delete")
    try:
        admin = create_engine(server.get_uri().replace("postgresql://", "postgresql+psycopg2://"))
        with admin.begin() as conn:
            conn.execute(text("CREATE ROLE clean_application LOGIN PASSWORD 'test' NOSUPERUSER NOCREATEDB NOCREATEROLE"))
            conn.execute(text("ALTER ROLE clean_application SET track_functions = 'all'"))
            if os.environ.get("PLAN_MODE"):
                conn.execute(text(f"ALTER ROLE clean_application SET plan_cache_mode = '{os.environ['PLAN_MODE']}'"))
            if EXPLAIN_MS:
                for k, v in (("session_preload_libraries", "auto_explain"), ("auto_explain.log_min_duration", f"{EXPLAIN_MS}ms"),
                             ("auto_explain.log_nested_statements", "on"), ("auto_explain.log_analyze", "on"),
                             ("auto_explain.log_level", "notice"), ("client_min_messages", "notice")):
                    conn.execute(text(f"ALTER ROLE clean_application SET {k} = '{v}'"))
        app = create_engine(admin.url.set(username="clean_application", password="test"))
        built = pr.core.initialize_database(admin, app)
        contract = pr.files.mdm_contract("iapd.adv", pr.FILINGS, root=root)
        with admin.begin() as conn:
            for statement in filter(None, os.environ.get("FIX_SQL", "").split(";")):
                conn.execute(text(statement))
            pr.register_dataset(conn, pr.FILINGS, built.registry, contract)
            policy = pr.register_policy(conn, pr.proving_policy(root, pr.digest({"filings": filings})))
        stats: dict = defaultdict(lambda: [0, 0.0])
        notices: list = []
        captured: dict = {}

        @event.listens_for(app, "before_cursor_execute")
        def _before(conn, cursor, statement, params, context, many):
            conn.info.setdefault("t", []).append(time.perf_counter())

        @event.listens_for(app, "after_cursor_execute")
        def _after(conn, cursor, statement, params, context, many):
            s = stats[shape(statement)]
            s[0] += 1
            s[1] += time.perf_counter() - conn.info["t"].pop()
            if "match_proposal_snapshot" in statement and isinstance(params, dict) and "scope" in params:
                captured["scope"] = json.loads(params["scope"]) if isinstance(params["scope"], str) else params["scope"]
            if statement.lstrip().startswith("SELECT body FROM mdm.decision WHERE") and "keys" in (params or {}):
                captured["decision_keys"] = params["keys"]
            if statement.lstrip().startswith("SELECT body FROM mdm.source_reading") and "keys" in (params or {}):
                captured["reading_keys"] = params["keys"]
            raw = cursor.connection
            if raw.notices:
                notices.extend(raw.notices)
                del raw.notices[:]

        stage = pr.MergeStage(pr.Store(app), closure_limit=10000)
        per_batch, done = [], 0
        prev_fn: dict = {}
        for month in sorted(filings):
            found, _ = pr.assertions(pr.FILINGS, contract, filings[month], month)
            for i in range(0, len(found), pr.BATCH):
                if done >= batches:
                    break
                stats.clear()
                notices.clear()
                started = time.perf_counter()
                stage.apply(batch_id=f"t-{month}-{i}", run_id=str(uuid4()), policy_digest=policy,
                            consumer="adv-tuning", expected_checkpoint=done, checkpoint=done + 1,
                            as_of=pr.AS_OF, assertions=found[i:i + pr.BATCH])
                total = time.perf_counter() - started
                if os.environ.get("ANALYZE_EACH"):
                    with admin.begin() as ac:
                        ac.execute(text("ANALYZE mdm.decision, mdm.source_reading, mdm.master_entity, mdm.stage_record"))
                time.sleep(1.2)  # backends flush function statistics when idle
                with admin.connect() as sc:
                    now_fn = {r[0]: (r[1], r[2]) for r in sc.execute(text(
                        "SELECT funcname, calls, total_time/1000 FROM pg_stat_user_functions"))}
                fn_delta = {k: round(v[1] - prev_fn.get(k, (0, 0))[1], 2) for k, v in now_fn.items()
                            if k in ("match_proposal_snapshot", "write_batch", "keep_stage", "record_company_version")}
                prev_fn.clear(); prev_fn.update(now_fn)
                sql = sum(v[1] for v in stats.values())
                per_batch.append({"batch": f"{month} {i}", "seconds": round(total, 2), "sql_seconds": round(sql, 2),
                                  "statements": {k: [v[0], round(v[1], 3)] for k, v in stats.items()}})
                print(json.dumps({**{k: per_batch[-1][k] for k in ("batch", "seconds", "sql_seconds")},
                                  "keys": len(captured.get("scope", {}).get("keys", [])), "fn": fn_delta}), flush=True)
                done += 1
        with admin.connect() as conn:
            print("functions (calls, total s, self s):")
            for r in conn.execute(text("SELECT funcname, calls, round(total_time::numeric/1000,2), round(self_time::numeric/1000,2) "
                                       "FROM pg_stat_user_functions ORDER BY total_time DESC LIMIT 15")):
                print("  ", tuple(r))
        with admin.connect() as conn:
            print("avg body bytes:", conn.execute(text(
                "SELECT (SELECT round(avg(pg_column_size(body))) FROM mdm.decision), "
                "(SELECT round(avg(pg_column_size(body))) FROM mdm.source_reading)")).one())
        if os.environ.get("PLAN_SPLIT"):
            keys = captured["scope"]["keys"]
            lit = "ARRAY[" + ",".join("'" + k.replace("'", "''") + "'" for k in keys) + "]::text[]"
            parts = {
                "evidence": f"SELECT count(*) FROM mdm.source_reading WHERE body->>'subject'=ANY({lit}) OR mdm.reading_link_subjects(body) && {lit}",
                "decisions": f"SELECT count(*) FROM mdm.decision WHERE decision_id=ANY({lit}) OR body->>'subject'=ANY({lit}) OR body->>'entity_id'=ANY({lit}) OR body->>'left'=ANY({lit}) OR body->>'right'=ANY({lit}) OR body->>'target'=ANY({lit})",
                "decisions joined": f"WITH k AS (SELECT DISTINCT unnest({lit}) AS key) SELECT count(*) FROM mdm.decision WHERE decision_id IN (SELECT decision_id FROM mdm.decision WHERE decision_id IN (SELECT key FROM k) "
                                    + "".join(f"UNION ALL SELECT d.decision_id FROM k JOIN mdm.decision d ON d.body->>'{c}'=k.key " for c in ("subject", "entity_id", "left", "right", "target")) + ")",
                "evidence joined": f"WITH k AS (SELECT DISTINCT unnest({lit}) AS key) SELECT count(*) FROM mdm.source_reading WHERE assertion_id IN (SELECT r.assertion_id FROM k JOIN mdm.source_reading r ON r.body->>'subject'=k.key UNION ALL SELECT assertion_id FROM mdm.source_reading WHERE mdm.reading_link_subjects(body) && {lit})",
            }
            with admin.connect() as conn:
                print("rows:", conn.execute(text("SELECT count(*) FROM mdm.decision")).scalar(), "keys", len(keys))
                print("datcollate:", conn.execute(text("SELECT datcollate, datlocprovider FROM pg_database WHERE datname=current_database()")).one())
                for name, sql in parts.items():
                    out = conn.execute(text("EXPLAIN (ANALYZE, SUMMARY) " + sql)).scalars().all()
                    print(f"  {name:18s}", [l for l in out if l.startswith(("Planning Time", "Execution Time"))])
                    for l in out:
                        if "Filter" in l or "Cond" in l:
                            l = re.sub(r"'\{[^}]*\}'", "'{..}'", l)
                        print("      ", l[:170])
        if os.environ.get("SNAP_SPLIT"):
            keys, sources = captured["scope"]["keys"], captured["scope"]["sources"]
            parts = {
                "readings_naming": "SELECT count(*) FROM mdm.readings_naming(CAST(:k AS text[]))",
                "decisions_naming": "SELECT count(*) FROM mdm.decisions_naming(CAST(:k AS text[]))",
                "  subject join": "EXPLAIN (ANALYZE, COSTS OFF) SELECT r.assertion_id FROM unnest(CAST(:k AS text[])) k(key) JOIN mdm.source_reading r ON r.body->>'subject' = k.key",
                "  link per key": "EXPLAIN (ANALYZE, COSTS OFF) SELECT s.assertion_id FROM unnest(CAST(:k AS text[])) k(key) JOIN mdm.source_reading s ON mdm.reading_link_subjects(s.body) @> ARRAY[k.key]",
                "  link GIN forced": "EXPLAIN (ANALYZE, COSTS OFF) SELECT assertion_id FROM mdm.source_reading WHERE mdm.reading_link_subjects(body) && CAST(:k AS text[]) AND current_setting('enable_seqscan') IS NOT NULL",
                "  link lookup": "EXPLAIN (ANALYZE, COSTS OFF) SELECT assertion_id FROM mdm.source_reading WHERE mdm.reading_link_subjects(body) && CAST(:k AS text[])",
                "identities": "SELECT count(*) FROM mdm.master_entity WHERE entity_id::text=ANY(CAST(:k AS text[]))",
                "current_entity": "SELECT count(*) FROM mdm.current_entity WHERE object_id=ANY(CAST(:k AS text[]))",
                "current_record": "SELECT count(*) FROM mdm.current_record WHERE (object_type='relationship' AND body->>'source_id'=ANY(CAST(:k AS text[]))) OR (object_type='relationship' AND body->>'target_id'=ANY(CAST(:k AS text[]))) OR (object_type='review' AND body->>'entity_id'=ANY(CAST(:k AS text[]))) OR (object_type='review' AND body->>'subject'=ANY(CAST(:k AS text[]))) OR (object_type='review' AND body->'affected_subjects' ?| CAST(:k AS text[]))",
                "whole snapshot": "SELECT mdm.match_proposal_snapshot(CAST(:s AS jsonb))",
                "rows+agg only": """WITH e AS (SELECT assertion_id AS id, body FROM mdm.source_reading WHERE assertion_id IN (SELECT id FROM mdm.readings_naming(CAST(:k AS text[])) id)),
                    d AS (SELECT decision_id AS id, body FROM mdm.decision WHERE decision_id IN (SELECT id FROM mdm.decisions_naming(CAST(:k AS text[])) id)),
                    a AS (SELECT 'source_reading' AS kind, id, body FROM e UNION ALL SELECT 'decision', id, body FROM d)
                    SELECT count(*) || ' rows ' || length(jsonb_agg(to_jsonb(a) ORDER BY kind, id)::text) || ' bytes' FROM a""",
            }
            with app.connect() as conn:
                print("keys", len(keys), "current_entity rows", conn.execute(text("SELECT count(*) FROM mdm.current_entity")).scalar())
                for name, sql in parts.items():
                    conn.execute(text("SET enable_seqscan = " + ("off" if "forced" in name else "on")))
                    t0 = time.perf_counter()
                    res = conn.execute(text(sql), {"k": keys, "s": json.dumps(captured["scope"])}).scalars().all()
                    print(f"  {name:18s} {time.perf_counter()-t0:6.3f}s  -> {str(res[0])[:12]}")
                    if sql.startswith("EXPLAIN"):
                        for l in res:
                            print("        ", re.sub(r"'\{[^}]*\}'", "'{..}'", l)[:150])
        if os.environ.get("ONLY_FUNCTIONS"):
            return
        with admin.connect() as conn:
            print("analyze stats:", conn.execute(text(
                "SELECT relname, n_live_tup, n_mod_since_analyze, last_autoanalyze IS NOT NULL, last_analyze IS NOT NULL "
                "FROM pg_stat_user_tables WHERE schemaname='mdm' AND relname IN ('decision','source_reading','stage_record','master_entity','current_record')")).all())
            keys = [r[0] for r in conn.execute(text("SELECT body->>'subject' FROM mdm.source_reading ORDER BY random() LIMIT 500"))]
            probe = ("SELECT count(*) FROM mdm.decision WHERE decision_id=ANY(:k) OR body->>'subject'=ANY(:k) "
                     "OR body->>'entity_id'=ANY(:k) OR body->>'left'=ANY(:k) OR body->>'right'=ANY(:k) OR body->>'target'=ANY(:k)")
            for label in ("before ANALYZE", "after ANALYZE"):
                plan = conn.execute(text("EXPLAIN (ANALYZE, BUFFERS) " + probe), {"k": keys}).scalars().all()
                print(label, "\n  " + "\n  ".join(plan[:12]))
                conn.execute(text("ANALYZE mdm.decision")); conn.commit()
            sizes = conn.execute(text("SELECT relname, n_live_tup FROM pg_stat_user_tables WHERE schemaname='mdm' "
                                      "ORDER BY n_live_tup DESC LIMIT 12")).all()
        (HERE / "explain-last-batch.txt").write_text("\n".join(re.sub(r"\{[^}]{200,}\}", "'{...}'", n) for n in notices))
        keys, sources = captured["scope"]["keys"], captured["scope"]["sources"]
        print("snapshot scope: keys", len(keys), "sources", len(sources))
        parts = {
            "evidence": "SELECT count(*) FROM mdm.source_reading WHERE body->>'subject'=ANY(CAST(:k AS text[])) OR mdm.reading_link_subjects(body) && CAST(:k AS text[])",
            "decisions": "SELECT count(*) FROM mdm.decision WHERE decision_id=ANY(CAST(:k AS text[])) OR body->>'subject'=ANY(CAST(:k AS text[])) OR body->>'entity_id'=ANY(CAST(:k AS text[])) OR body->>'left'=ANY(CAST(:k AS text[])) OR body->>'right'=ANY(CAST(:k AS text[])) OR body->>'target'=ANY(CAST(:k AS text[])) OR (operation='retire_source' AND body->>'source_code'=ANY(CAST(:s AS text[])))",
            "identities": "SELECT count(*) FROM mdm.master_entity i WHERE entity_id::text=ANY(CAST(:k AS text[]))",
            "projections": "SELECT count(*) FROM (SELECT 1 FROM mdm.current_entity WHERE object_id=ANY(CAST(:k AS text[])) UNION ALL SELECT 1 FROM mdm.current_record WHERE (object_type='relationship' AND body->>'source_id'=ANY(CAST(:k AS text[]))) OR (object_type='relationship' AND body->>'target_id'=ANY(CAST(:k AS text[]))) OR (object_type='review' AND body->>'entity_id'=ANY(CAST(:k AS text[]))) OR (object_type='review' AND body->>'subject'=ANY(CAST(:k AS text[]))) OR (object_type='review' AND body->'affected_subjects' ?| CAST(:k AS text[]))) x",
        }
        with app.connect() as conn:
            for mode in ("auto", "force_generic_plan"):
                conn.execute(text(f"SET plan_cache_mode = {mode}"))
                for name, sql in parts.items():
                    t0 = time.perf_counter()
                    plan = conn.execute(text("EXPLAIN (ANALYZE) " + sql), {"k": keys, "s": sources}).scalars().all()
                    print(f"{mode:20s} {name:12s} {time.perf_counter()-t0:7.3f}s  {plan[-1]}  top: {plan[1].strip()[:90] if len(plan)>1 else ''}")
        with app.connect() as conn:
            t0 = time.perf_counter()
            conn.execute(text("SELECT mdm.match_proposal_snapshot(CAST(:s AS jsonb))"), {"s": json.dumps(captured["scope"])})
            print(f"whole snapshot function {time.perf_counter()-t0:.3f}s")
            for mode in ("force_generic_plan", "force_custom_plan", "auto"):
                conn.execute(text(f"SET plan_cache_mode = {mode}"))
                for _ in range(2):
                    t0 = time.perf_counter()
                    conn.execute(text("SELECT mdm.match_proposal_snapshot(CAST(:s AS jsonb))"), {"s": json.dumps(captured["scope"])})
                    print(f"  snapshot, plan_cache_mode={mode}: {time.perf_counter()-t0:.3f}s")
            conn.execute(text("RESET plan_cache_mode"))
            body = """WITH evidence AS (SELECT assertion_id AS id,body FROM mdm.source_reading WHERE body->>'subject'=ANY(CAST(:k AS text[])) OR mdm.reading_link_subjects(body) && CAST(:k AS text[]) LIMIT 10001),
              decisions AS (SELECT decision_id AS id,body FROM mdm.decision WHERE decision_id=ANY(CAST(:k AS text[])) OR body->>'subject'=ANY(CAST(:k AS text[])) OR body->>'entity_id'=ANY(CAST(:k AS text[])) OR body->>'left'=ANY(CAST(:k AS text[])) OR body->>'right'=ANY(CAST(:k AS text[])) OR body->>'target'=ANY(CAST(:k AS text[])) LIMIT 10001),
              all_rows AS (SELECT 'source_reading' AS kind,id,body FROM evidence UNION ALL SELECT 'decision',id,body FROM decisions)"""
            for label, tail in (("agg", "SELECT count(*), coalesce(jsonb_agg(to_jsonb(a) ORDER BY kind,id),'[]') FROM all_rows a"),):
                t0 = time.perf_counter()
                n, snap = conn.execute(text(body + tail), {"k": keys}).one()
                t1 = time.perf_counter()
                size = len(json.dumps(snap))
                conn.execute(text("SELECT encode(sha256(convert_to(CAST(:j AS jsonb)::text,'UTF8')),'hex')"), {"j": json.dumps(snap)})
                t2 = time.perf_counter()
                conn.execute(text("SELECT count(*) FROM (SELECT 1 FROM jsonb_array_elements(CAST(:j AS jsonb)) r GROUP BY r->>'kind' HAVING count(*)>10000) x"), {"j": json.dumps(snap)})
                t3 = time.perf_counter()
                print(f"rows {n} snapshot {size/1e6:.1f} MB; agg {t1-t0:.3f}s, hash {t2-t1:.3f}s, group check {t3-t2:.3f}s")
        dk, rk = captured["decision_keys"], captured["reading_keys"]
        cols = ["subject", "entity_id", "left", "right", "target"]
        variants = {
            "decision now": ("SELECT body FROM mdm.decision WHERE body->>'subject'=ANY(:k) OR body->>'entity_id'=ANY(:k) OR body->>'left'=ANY(:k) "
                             "OR body->>'right'=ANY(:k) OR body->>'target'=ANY(:k) OR decision_id=ANY(:k)", dk),
            "decision joined": ("WITH k AS (SELECT DISTINCT unnest(CAST(:k AS text[])) AS key) SELECT body FROM mdm.decision WHERE decision_id IN ("
                                "SELECT decision_id FROM mdm.decision WHERE decision_id IN (SELECT key FROM k) UNION ALL "
                                + " UNION ALL ".join(f"SELECT d.decision_id FROM k JOIN mdm.decision d ON d.body->>'{c}'=k.key" for c in cols) + ")", dk),
            "reading now": ("SELECT body FROM mdm.source_reading WHERE body->>'subject'=ANY(:k) OR mdm.reading_link_subjects(body) && CAST(:k AS text[])", rk),
            "reading joined": ("WITH k AS (SELECT DISTINCT unnest(CAST(:k AS text[])) AS key) SELECT body FROM mdm.source_reading WHERE assertion_id IN ("
                               "SELECT r.assertion_id FROM k JOIN mdm.source_reading r ON r.body->>'subject'=k.key UNION ALL "
                               "SELECT assertion_id FROM mdm.source_reading WHERE mdm.reading_link_subjects(body) && CAST(:k AS text[]))", rk),
        }
        with app.connect() as conn:
            for name, (sql, keys_) in variants.items():
                t0 = time.perf_counter(); n = len(conn.execute(text(sql), {"k": keys_}).all()); t1 = time.perf_counter()
                plan = conn.execute(text("EXPLAIN " + sql), {"k": keys_}).scalars().all()
                print(f"{name:16s} keys {len(keys_):5d} rows {n:5d} {t1-t0:6.3f}s  plan: " + " | ".join(l.strip()[:60] for l in plan if "Scan" in l or "Join" in l)[:400])
        first, last = per_batch[0]["statements"], per_batch[-1]["statements"]
        growth = sorted(((last[k][1] - first.get(k, [0, 0])[1], last[k][0], first.get(k, [0, 0])[1], last[k][1], k)
                         for k in last), reverse=True)[:12]
        print("\nTop growth first->last batch (delta s, calls, first s, last s, statement):")
        for g in growth:
            print(f"{g[0]:7.2f} {g[1]:6d} {g[2]:7.2f} {g[3]:7.2f}  {g[4]}")
        print("\nRows:", [(r[0], r[1]) for r in sizes])
        (HERE / "profile.json").write_text(json.dumps(per_batch, indent=1) + "\n")
    finally:
        server.cleanup()


if __name__ == "__main__":
    main(Path(sys.argv[1]), Path(sys.argv[2]), int(sys.argv[3]))
