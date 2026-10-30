"""Ticket 48: the cohort's financials end to end, on the installed path.

Ticket 47 matched every measure with the answer key's rules in a disposable PostgreSQL, the
filers' SIC and place read from their submissions files. Here the installed bundle does the
work, on empty stores of its own (as ticket 135's proof):

1. The cohort's Companies are mastered by the SEC Company `mastering` target: the installed
   `mdm prepare-clean-company` writes one bundle of the cohort's Company documents (with 135's
   population and Name Census), and the installed workers run it, each step checked by a
   verifier under its own login. The store setup and the run are 135's
   (`.scratch/mastering-to-done/proof/installed_mastering_proof.py`), reused, not copied.
2. Silver is initialized and its three tables registered from their specs; each company facts
   file is read by facts.yaml's `company_fact` (the configured engine) and the rows landed by
   `silver land`, then again on its first 10,000 rows (which must change nothing); `silver line-items` and
   `silver measures` build the rest, the measures reading each filer's statement format and
   country from its Company master.
3. Everything is read back from the stored tables: rows per line item and measure, coverage by
   fiscal year, each null with its reason, each line item's filing found among the filer's
   facts, each measure's line-item inputs found among the stored line items, and the measures
   equal to the answer key's rules (47's oracle, fed each filer's SIC and place from its
   submissions file) and to the hand-checked answer key itself. An agent's view of the table
   comes from `silver describe`.

Inputs, on this machine only (no provider request): the cohort's company facts files, the
submissions capture `all-76230`, and `<work>/documents-cohort.json` (the cohort's Company
documents among 135's 6,726), `population.json` and `census.json` (135's). The report holds
counts only.

Run it with COHORT_PROOF_SAMPLE=1 first (minutes), then without (about 45 minutes):

    COHORT_PROOF_OUT=<report.json> PATH="$HOME/.cargo/bin:$PATH" \\
      uv run --no-sync pytest -q -s -p no:randomly .scratch/company-financials/proof/cohort_proof.py
"""

from __future__ import annotations

import gzip
import importlib.util
import json
import os
import sys
import time
from collections import Counter
from concurrent.futures import ProcessPoolExecutor
from decimal import ROUND_HALF_UP, Decimal, getcontext
from pathlib import Path

from sqlalchemy import create_engine, text

from edgar_warehouse.mdm.clean.store import migrate, register_policy
from edgar_warehouse.bookkeeping.clean.database import grant_profile
from edgar_warehouse.bookkeeping.clean.destinations import migrate_guard
from edgar_warehouse.rules import files
from edgar_warehouse.rules.source_engine import SourceEngine
from tests.engine.test_data_skill_bundle_postgres import _run, _stores, installed  # noqa: F401
from tests.integration.test_configured_bookkeeping_postgres import databases  # noqa: F401
from tests.support.rules_approval import approve
from tests.support.rules_authority import register_dataset

HERE = Path(__file__).resolve()
REPO = HERE.parents[3]
DATA = Path("~/.local/share/edgartools/clean-mdm").expanduser()
COHORT = DATA / "proving/company-facts/cohort"
KEY = DATA / "proving/company-facts/answer-key.json"
WORK = Path(os.environ.get("COHORT_PROOF_WORK", DATA / "proving/company-facts/proof-48"))
SUBMISSIONS = DATA / "captures/sec.submissions.company/all-76230/bronze"
FACTS = files.ROOT / "sources" / "sec.company-facts"
SPECS = ("silver-company-fact.yaml", "silver-company-line-item.yaml", "silver-company-measure.yaml")
SILVER_RUNTIME = "silver_runtime"
PLACES = Decimal("1e-10")
HALF_STEP = Decimal("0.5e-10") + Decimal("0.5e-12")


def _module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# 135's harness: its store setup, its Company pipeline and its inputs (bound as attributes, so
# pytest does not collect its test here).
m135 = _module("installed_mastering_proof", REPO / ".scratch/mastering-to-done/proof/installed_mastering_proof.py")
sys.argv[1:] = [str(COHORT), "/nonexistent", "/nonexistent", "/nonexistent"]  # the oracle reads its paths at import
sys.path.insert(0, str(REPO / ".scratch/company-financials/answer-key"))
import oracle  # noqa: E402


def filed(cik: str) -> tuple[str | None, str | None]:
    """A filer's SIC and place of incorporation from its latest captured submissions file (as the key reads them)."""
    found = sorted((SUBMISSIONS / "submissions/sec" / f"cik={int(cik)}").rglob(f"CIK{cik}.json"))
    if not found:
        return None, None
    body = json.loads(found[-1].read_bytes())
    return (str(body["sic"]) if body.get("sic") else None, body.get("stateOfIncorporation") or None)


def fact_rows(path: Path) -> list[dict]:
    return SourceEngine(files.load(FACTS / "facts.yaml")).read(gzip.decompress(path.read_bytes())).tables["company_fact"]


def expected(job: tuple[Path, tuple]) -> dict:
    """47's oracle for one filer: every measure, rounded once to silver's 10 places."""
    path, (sic, place) = job
    oracle.PLACES = PLACES
    getcontext().rounding = ROUND_HALF_UP
    cik = path.name[:10]
    body = json.loads(gzip.decompress(path.read_bytes()), parse_float=Decimal)
    company = oracle.Company(cik, body, sic, place)
    items = {y: {name: oracle.item(company, y, name) for name in oracle.LISTS["us-gaap"]} for y in sorted(company.years)}
    return {(cik, m["measure"], int(m["year"]), m["window"] or 1): m for m in oracle.measures(company, items)}


def same(want: dict, value, reason) -> bool:
    return (None if want["value"] is None else Decimal(want["value"])) == value and want["reason"] == reason


def test_cohort_financials_end_to_end(installed, databases, tmp_path):  # noqa: F811
    python, root = installed
    out = Path(os.environ["COHORT_PROOF_OUT"])
    started, timings = time.monotonic(), {}
    paths = sorted(COHORT.glob("*.json.gz"))
    # COHORT_PROOF_SAMPLE=1: the answer key's filers only, every step through the installed commands in
    # minutes, so a fault in a late step shows before the full run (ticket 48: two full runs lost to one).
    sample = bool(os.environ.get("COHORT_PROOF_SAMPLE"))
    if sample:
        paths = [p for p in paths if p.name[:10] in json.loads(KEY.read_text())["companies"]]
    documents = json.loads((WORK / "documents-cohort.json").read_text())

    def mark(stage: str) -> None:
        timings[stage] = round((time.monotonic() - started) / 60, 1)
        print(json.dumps({"stage": stage, "minutes": timings[stage]}), flush=True)

    # Provisioning (harness), as 135: an empty MDM store with its fence, the policy, the Company contract.
    for profile in (*m135.PROFILES, "mdm.merge", "journal.record"):
        grant_profile(databases.admin, profile=profile, worker="bk_runtime", verifier="bk_verifier")
    server = databases.admin.execution_options(isolation_level="AUTOCOMMIT")
    with server.connect() as conn:
        conn.exec_driver_sql("CREATE DATABASE mdm_proof")
        conn.exec_driver_sql("CREATE DATABASE silver_proof")
        conn.exec_driver_sql(f"CREATE ROLE {SILVER_RUNTIME} LOGIN PASSWORD 'test' NOSUPERUSER NOCREATEDB NOCREATEROLE")
    mdm_admin = create_engine(databases.admin.url.set(database="mdm_proof"))
    mdm_app = create_engine(mdm_admin.url.set(username="clean_application", password="test"))
    migrate(mdm_admin, application_role="clean_application")
    migrate_guard(mdm_admin, runtime_role="clean_application")
    with mdm_admin.begin() as conn:
        policy = register_policy(conn, files.policy())
        register_dataset(conn, m135.SEC, "1", files.mdm_contract("sec.submissions.company", m135.SEC))
        conn.exec_driver_sql("GRANT USAGE ON SCHEMA mdm TO bk_verifier")
        conn.exec_driver_sql("GRANT SELECT ON ALL TABLES IN SCHEMA mdm TO bk_verifier")
        conn.exec_driver_sql("GRANT SELECT ON ALL TABLES IN SCHEMA public TO bk_verifier")
    mdm_reader = create_engine(mdm_admin.url.set(username="bk_verifier", password="test"))
    silver_owner = create_engine(databases.admin.url.set(database="silver_proof"))
    silver_runtime = create_engine(silver_owner.url.set(username=SILVER_RUNTIME, password="test"))

    url = lambda engine: engine.url.render_as_string(hide_password=False)  # noqa: E731
    env = {**_stores(databases), "BOOKKEEPING_MANIFEST_ROOT": (tmp_path / "control").as_uri()}
    worker = {**env, "MDM_DATABASE_URL": url(mdm_app), "MDM_APPLICATION_ROLE": "clean_application"}
    verifier = {**env, "BOOKKEEPING_DATABASE_URL": url(databases.verifier), "MDM_DATABASE_URL": url(mdm_reader)}
    silver = {**env, "SILVER_MIGRATION_DATABASE_URL": url(silver_owner), "SILVER_DATABASE_URL": url(silver_runtime),
              "MDM_DATABASE_URL": url(mdm_reader)}

    def cli(*args, env=env):
        done = _run(python, "-m", "edgar_warehouse.cli", *args, env=env, cwd=root)
        assert done.returncode == 0, done.stderr[-4000:]
        return done.stdout

    # 1. The cohort's Companies, mastered by the installed Company target.
    report = json.loads(cli(
        "mdm", "prepare-clean-company", "--capture", str(m135.CAPTURE), "--documents", str(WORK / "documents-cohort.json"),
        "--population", str(WORK / "population.json"), "--name-census", str(WORK / "census.json"),
        "--catalog", m135.CATALOG, "--capture-run", "local-cm27-cohort-t48", "--catalog-run", m135.CATALOG_RUN,
        "--observed-at", m135.OBSERVED_AT, "--output", str(tmp_path / "sec"), "--as-of", m135.old.AS_OF,
        "--revision", "0"))
    assert report["policy_digest"] == policy and report["manifest"]
    pipeline = m135.PIPELINE["pipeline"]
    saved = databases.rules.save("pipeline", pipeline, "1", m135.PIPELINE)
    databases.rules.prove("pipeline", pipeline, "1", {"digest": saved["digest"], "passed": True,
                                                      "batch_hash": report["manifest"]["sha256"]})
    approve(databases.approver, "pipeline", pipeline, "1")
    databases.rules.activate("pipeline", pipeline, "1")
    run_id = json.loads(cli("rules", "run", "--pipeline", pipeline, "--target", "sec", "--input-manifest",
                            report["manifest"]["uri"], "--input-sha256", report["manifest"]["sha256"]))["run"]["run_id"]

    def drive(profiles: tuple[str, ...], steps: set[str] | None = None) -> None:
        deadline = time.monotonic() + 3600
        while True:
            for profile in profiles:
                cli("workers", "work", profile, run_id, "--limit", m135.LIMIT, env=worker)
                cli("workers", "verify", profile, run_id, "--reports", (tmp_path / "reports").as_uri(),
                    "--limit", m135.LIMIT, env=verifier)
            mine = [i for i in json.loads(cli("bookkeeping", "status", run_id))["items"]
                    if steps is None or i["step"] in steps]
            if mine and all(i["state"] == "verified" for i in mine):
                return
            assert not [i for i in mine if i["state"] in ("failed", "rejected")], mine[:3]
            assert time.monotonic() < deadline
            time.sleep(2)

    drive(m135.PROFILES, {step["name"] for step in m135.MASTERING[:-2]})
    drive(("mdm.merge", "journal.record"))
    cli("bookkeeping", "finalize", run_id)
    assert json.loads(cli("bookkeeping", "status", run_id))["run"]["state"] == "complete"
    mark("companies mastered")

    # 2. Silver: initialized, the three tables registered, the facts landed twice, then built.
    cli("silver", "init", "--runtime-role", SILVER_RUNTIME, env=silver)
    for spec in SPECS:
        assert json.loads(cli("silver", "register", str(FACTS / spec), "--runtime-role", SILVER_RUNTIME,
                              env=silver))["created"] is True
    rows_file = tmp_path / "company_fact.jsonl"
    read = Counter()
    with ProcessPoolExecutor() as pool, rows_file.open("w") as rows_out:
        for path, rows in zip(paths, pool.map(fact_rows, paths, chunksize=4)):
            read["files"] += 1
            read["files with facts"] += bool(rows)
            read["rows"] += len(rows)
            for row in rows:
                rows_out.write(json.dumps(row, default=str) + "\n")
    mark("facts read")
    first = json.loads(cli("silver", "land", "company_fact", str(rows_file), env=silver))
    # A second landing changes nothing: shown on the first rows, not by landing every fact again.
    again_file = tmp_path / "company_fact-again.jsonl"
    with rows_file.open() as rows_in, again_file.open("w") as again_out:
        again_out.writelines(line for _, line in zip(range(10_000), rows_in))
    again = json.loads(cli("silver", "land", "company_fact", str(again_file), env=silver))
    assert (again["inserted"], again["changed"]) == (0, 0), again
    mark("facts landed")
    built = {"line_items": json.loads(cli("silver", "line-items", env=silver)),
             "measures": json.loads(cli("silver", "measures", env=silver))}
    mark("built")
    described = json.loads(cli("silver", "describe", "company_measure", env=silver))

    # 3. Read back from the stored tables.
    with silver_runtime.connect() as conn:
        one = lambda sql: conn.execute(text(sql)).scalar()  # noqa: E731
        groups = lambda sql: {str(k): v for k, v in conn.execute(text(sql)).all()}  # noqa: E731
        stored = {
            "company_fact": one("SELECT count(*) FROM silver.company_fact"),
            "company_fact_companies": one("SELECT count(DISTINCT company_key) FROM silver.company_fact"),
            "company_fact_with_mdm_id": one("SELECT count(*) FROM silver.company_fact WHERE company_mdm_id IS NOT NULL"),
            "company_line_item": one("SELECT count(*) FROM silver.company_line_item"),
            "company_measure": one("SELECT count(*) FROM silver.company_measure"),
            "company_measure_with_mdm_id": one(
                "SELECT count(*) FROM silver.company_measure WHERE company_mdm_id IS NOT NULL"),
        }
        line_items = groups("SELECT line_item, count(value) FILTER (WHERE value IS NOT NULL) || ' of ' || count(*) "
                            "FROM silver.company_line_item GROUP BY 1 ORDER BY 1")
        line_reasons = groups("SELECT coalesce(null_reason, '(value)'), count(*) FROM silver.company_line_item "
                              "GROUP BY 1 ORDER BY 2 DESC")
        measures = groups("SELECT measure || ':' || window_years, count(value) FILTER (WHERE value IS NOT NULL) "
                          "|| ' of ' || count(*) FROM silver.company_measure GROUP BY 1 ORDER BY 1")
        measure_reasons = groups("SELECT coalesce(null_reason, '(value)'), count(*) FROM silver.company_measure "
                                 "GROUP BY 1 ORDER BY 2 DESC")
        by_year = groups("SELECT fiscal_year, count(DISTINCT company_key) || ' companies, ' || count(value) "
                         "|| ' line items with a value' FROM silver.company_line_item GROUP BY 1 ORDER BY 1")
        traced = {
            "line items with a value": one("SELECT count(*) FROM silver.company_line_item WHERE value IS NOT NULL"),
            "with a filing": one("SELECT count(*) FROM silver.company_line_item WHERE value IS NOT NULL "
                                 "AND accession IS NOT NULL"),
            "filing found among the filer's facts": one(
                "SELECT count(*) FROM silver.company_line_item l WHERE l.value IS NOT NULL AND EXISTS ("
                "SELECT 1 FROM silver.company_fact f WHERE f.company_key = l.company_key "
                "AND f.accession = l.accession)"),
        }
        got = {(r.company_key, r.measure, r.fiscal_year, r.window_years): r for r in conn.execute(text(
            "SELECT company_key, measure, fiscal_year, window_years, value, null_reason, inputs "
            "FROM silver.company_measure"))}
        stored_lines = {(r.company_key, r.fiscal_year, r.value) for r in conn.execute(text(
            "SELECT company_key, fiscal_year, value::text AS value FROM silver.company_line_item WHERE value IS NOT NULL"))}

    # Each measure's line-item inputs among the stored line items.
    inputs, unstored = Counter(), Counter()

    def traced_to_lines(cik: str, item: dict, year=None) -> bool:
        """A stored line item; or a computed figure (free cash flow, NOPAT) whose every part is one.
        A part names its value, concept and filing; its year is the figure's."""
        year = item.get("fiscal_year", year)
        if (cik, year, item.get("value")) in stored_lines:
            return True
        parts = [p for p in item.values() if isinstance(p, dict) and "value" in p]
        return bool(parts) and all(traced_to_lines(cik, p, year) for p in parts)
    for (cik, _, _, _), row in got.items():
        if row.value is None:
            continue
        inputs["measures with a value"] += 1
        # `inputs` maps each input (a line item, or a CAGR's start and end) to its fiscal year and figure.
        named = [(i.get("fiscal_year"), i.get("value")) for i in (row.inputs or {}).values() if isinstance(i, dict)]
        inputs["inputs named"] += bool(named)
        found = bool(named) and all(traced_to_lines(cik, i) for i in row.inputs.values() if isinstance(i, dict))
        inputs["every input stored"] += found
        if not found:
            unstored[row.measure] += 1

    # The measures against the answer key's rules, each filer's SIC and place from its submissions file.
    companies = {p.name[:10]: filed(p.name[:10]) for p in paths}
    want: dict = {}
    with ProcessPoolExecutor() as pool:
        for part in pool.map(expected, [(p, companies[p.name[:10]]) for p in paths], chunksize=4):
            want.update(part)
    from edgar_warehouse.financials import measures as measure_build
    mastered = measure_build.from_company(mdm_reader, set(companies))
    masters = {"cohort": len(companies), "with a Company master": len(mastered),
               "master's SIC and place equal the submissions file's": sum(
                   1 for cik, fields in mastered.items() if fields == companies[cik])}
    shape = lambda v: "empty" if v is None else f"{type(v).__name__} of {len(str(v))}"  # noqa: E731
    masters["how they differ"] = dict(Counter(
        f"{name}: master {shape(m)}, file {shape(f)}" + (", master ends with file" if m and f and str(m).endswith(str(f)) else "")
        for cik, fields in mastered.items() for name, m, f in zip(("sic", "place"), fields, companies[cik]) if m != f))
    rules_match, differ = Counter(), Counter()
    for key in set(want) | set(got):
        w, g = want.get(key), got.get(key)
        if w is None or g is None:
            rules_match["only in the key" if g is None else "only in silver"] += 1
        elif same(w, g.value, g.null_reason):
            rules_match["equal"] += 1
        else:
            rules_match["different"] += 1
            differ[("mastered" if key[0] in mastered else "no Company master") + ": "
                   + (g.null_reason or "(value differs)")] += 1
    hand = Counter()
    for cik, company in json.loads(KEY.read_text())["companies"].items():
        for m in company["measures"]:
            g = got.get((cik, m["measure"], int(m["year"]), m["window"] or 1))
            hand["compared"] += 1
            # The hand key keeps 12 places, silver 10 (ticket 47): equal when the key's value lies within silver's
            # rounding of it (half a 10th place, plus the key's own half a 12th place). Rounding the key again
            # to 10 places would round twice and move 4 of 1,600 by one in the last place.
            close = g is not None and m["reason"] == g.null_reason and (
                (m["value"] is None and g.value is None) or (m["value"] is not None and g.value is not None
                                                            and abs(Decimal(m["value"]) - g.value) <= HALF_STEP))
            hand["equal" if close else "different"] += 1
    mark("read back")

    result = {"files": read, "masters": masters, "landed": {"first": first, "again": again}, "built": built, "stored": stored,
              "line_items": line_items, "line_item_null_reasons": line_reasons, "measures": measures,
              "measure_null_reasons": measure_reasons, "coverage_by_year": by_year, "traced": traced,
              "measure_inputs": dict(inputs), "inputs not stored, by measure": dict(unstored), "rules_match": dict(rules_match), "differences_by_reason": dict(differ),
              "answer_key": dict(hand), "agent_view": sorted(described) if isinstance(described, dict) else None,
              "minutes": timings}
    out.write_text(json.dumps(result, indent=1, default=str))
    print(json.dumps(result, indent=1, default=str))
    assert read["files"] == (3 if sample else 368)
    assert stored["company_fact"] == read["rows"] == first["inserted"]
    assert hand["equal"] == hand["compared"] > 0
    assert inputs["every input stored"] == inputs["measures with a value"] > 0
    assert traced["filing found among the filer's facts"] == traced["with a filing"] == traced["line items with a value"]
