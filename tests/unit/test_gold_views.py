"""The Gold views, rendered from destination/gold/gold.yaml and run on an invented fixture (data-modeling skill, GOLD.md).

The fixture has four companies (one merged into another), two securities, a joint filing and a holding whose
security was never mastered. Each test is one of the skill's proofs; the rendered Snowflake text is checked apart.
"""
import json
import sqlite3
from datetime import date

import pytest

from edgar_warehouse.gold import views
from edgar_warehouse.rules import files

NAMES = files.load(files.ROOT / "snowflake.yaml")
DEST, MIRROR = NAMES["gold"]["database"], NAMES["mirror"]["database"]


def body(entity, kind, name, canonical=None, status="active"):
    return json.dumps({"entity_id": entity, "canonical_id": canonical or entity, "kind": kind, "status": status,
                       "fields": {"name": {"value": name}}})


@pytest.fixture()
def db():
    conn = sqlite3.connect(":memory:")
    conn.executescript("""
        create table mastering_master (entity_id text, canonical_id text, kind text, status text, body text);
        create table mastering_identifier (namespace text, value text, entity_id text);
        create table thirteenf_filing (accession_number text, cik text, form text, filing_date text, report_date text,
                                       primary_document text);
        create table thirteenf_holding (accession_number text, holding_index integer, cusip text, shares_held real,
                                        share_type text, market_value real, put_call text, discretion_type text,
                                        voting_auth_sole real, voting_auth_shared real, voting_auth_none real);
        create table master_binding (source_code text, source_key text, kind text, master_id text);
    """)
    masters = [("c1", body("c1", "company", "Alpha Capital")), ("c2", body("c2", "company", "Beta Partners")),
               ("c3", body("c3", "company", "Alpha Cap Old", canonical="c1", status="alias")),
               ("c4", body("c4", "company", "Delta Fund")),
               ("s1", body("s1", "security", "Alpha Common")), ("s2", body("s2", "security", "Beta Notes"))]
    conn.executemany("insert into mastering_master values (?, ?, ?, ?, ?)",  # the columns, and the body that holds the name
                     [(e, b["canonical_id"], b["kind"], b["status"], json.dumps({"fields": b["fields"]})) for e, b in
                      ((e, json.loads(text)) for e, text in masters)])
    conn.executemany("insert into mastering_identifier values (?, ?, ?)",
                     [("cik", "0000000001", "c1"), ("cik", "0000000002", "c2"), ("cusip", "AAA111", "s1")])
    conn.executemany("insert into thirteenf_filing values (?,?,?,?,?,?)", [
        ("f1", "1", "13F-HR", "2026-02-10", "2025-12-31", "a.xml"),
        ("f2", "1", "13F-HR", "2026-02-11", "2025-12-31", "b.xml"),  # a joint filing: two managers
        ("f2", "2", "13F-HR", "2026-02-11", "2025-12-31", "b.xml"),
        ("f3", "9", "13F-NT", "2026-02-12", "2025-12-31", "c.xml"),   # a manager that was never mastered
        ("f4", "3", "13F-HR", "2026-02-13", "2025-12-31", "d.xml")])  # a merged-away manager id
    conn.executemany("insert into thirteenf_holding values (?,?,?,?,?,?,?,?,?,?,?)", [
        ("f1", 1, "AAA111", 100, "SH", 1000.5, None, "SOLE", 100, 0, 0),
        ("f1", 2, "BBB222", 50, "SH", 250.25, None, "SOLE", 50, 0, 0),
        ("f2", 1, "AAA111", 10, "SH", 99.0, "Call", "SOLE", 10, 0, 0),
        ("f3", 1, "ZZZ999", 5, "PRN", 5.0, None, "SOLE", 5, 0, 0),   # no master security
        ("f4", 1, "AAA111", 7, "SH", 70.0, None, "SOLE", 7, 0, 0)])
    conn.executemany("insert into master_binding values (?,?,?,?)", [
        ("sec.company.v1", "1", "company", "c1"), ("sec.company.v1", "2", "company", "c2"),
        ("sec.company.v1", "3", "company", "c3"),  # bound to a master that merged away: the dimension answers for its survivor
        ("sec.thirteenf.securities.v2", "AAA111", "security", "s1"),
        ("sec.thirteenf.securities.v2", "BBB222", "security", "s2")])
    for statement in views.render(dialect="sqlite", qualify=False).values():
        conn.execute(statement)
    return conn


def rows(conn, sql):
    return conn.execute(sql).fetchall()


def test_every_object_names_its_requirement_and_every_link_names_a_dimension_that_exists():
    config = views.load()
    names = {item["name"] for item in config["objects"]}
    for item in config["objects"]:
        assert config["requirements"][item["requirement"]] and item["grain"], item["name"]
        for link in item.get("links", []) + ([item["parent"]["single_link"]] if "parent" in item else []):
            assert link["dimension"] in names


def test_a_fact_key_is_unique_and_never_null(db):
    for fact, key in (("fact_thirteenf_holding", "accession_number, holding_index"),
                      ("fact_thirteenf_filing", "accession_number, cik")):
        joined = "||'|'||".join(key.split(", "))
        assert rows(db, f"select count(*) - count(distinct {joined}), count(*) - count({key.split(', ')[0]}) from {fact}") == [(0, 0)]


def test_a_join_to_a_dimension_changes_no_row_count(db):
    assert rows(db, "select count(*) from fact_thirteenf_holding") == rows(db, "select count(*) from thirteenf_holding")
    assert rows(db, "select count(*) from fact_thirteenf_filing") == rows(db, "select count(*) from thirteenf_filing")


def test_every_dimension_key_resolves_including_the_two_reserved_members(db):
    for fact, key, dim in (("fact_thirteenf_holding", "held_key", "dim_security"),
                           ("fact_thirteenf_holding", "manager_key", "dim_company"),
                           ("fact_thirteenf_filing", "manager_key", "dim_company")):
        assert rows(db, f"select count(*) from {fact} f left join {dim} d on d.entity_id = f.{key} "
                        f"where d.entity_id is null") == [(0,)], (fact, key)


def test_a_dimension_has_one_row_per_canonical_master_and_never_an_alias(db):
    assert rows(db, "select entity_id from dim_company order by 1") == [("c1",), ("c2",), ("c4",), ("not-applicable",), ("unknown",)]
    assert rows(db, "select entity_id from dim_security order by 1") == [("not-applicable",), ("s1",), ("s2",), ("unknown",)]
    assert rows(db, "select cik from dim_company where entity_id = 'c1'") == [("0000000001",)]


def test_a_merged_away_id_finds_the_master_it_became(db):
    assert rows(db, "select manager_key from fact_thirteenf_filing where accession_number = 'f4'") == [("c1",)]


def test_an_unmastered_id_is_the_unknown_member_and_is_never_dropped(db):
    assert rows(db, "select manager_key from fact_thirteenf_filing where accession_number = 'f3'") == [("unknown",)]
    assert rows(db, "select held_key from fact_thirteenf_holding where accession_number = 'f3'") == [("unknown",)]


def test_a_holding_takes_its_manager_from_a_filing_with_one_and_not_applicable_from_a_joint_filing(db):
    got = dict(rows(db, "select accession_number, manager_key from fact_thirteenf_holding"))
    assert got["f1"] == "c1" and got["f2"] == "not-applicable" and got["f4"] == "c1"


def test_a_holding_takes_its_dates_from_the_filing_once(db):
    assert rows(db, "select business_date, recorded_date from fact_thirteenf_holding where accession_number = 'f2'") \
        == [("2025-12-31", "2026-02-11")]


def test_a_total_over_the_fact_equals_the_total_over_silver(db):
    for column in ("market_value", "shares_held"):
        assert rows(db, f"select sum({column}) from fact_thirteenf_holding") == rows(db, f"select sum({column}) from thirteenf_holding")


def test_the_calendar_has_one_row_per_day(db):
    days = (date(2035, 12, 31) - date(1994, 1, 1)).days + 1
    assert rows(db, "select count(*), min(date_key), max(date_key) from dim_date") == [(days, "1994-01-01", "2035-12-31")]
    assert rows(db, "select year, month from dim_date where date_key = '2026-02-10'") == [(2026, 2)]


def test_the_snowflake_text_is_qualified_reads_the_mirror_and_replaces_a_view():
    text = views.render()
    assert text["master"].startswith(f"CREATE OR REPLACE VIEW {DEST}.GOLD.master AS")
    assert f"FROM {MIRROR}.MDM.mastering_master" in text["master"]
    assert "SELECT entity_id, canonical_id, kind, status," in text["master"]  # columns, never parsed from the body
    assert "PARSE_JSON(body):fields.name.value::VARCHAR" in text["master"] and "PARSE_JSON(body):kind" not in text["master"]
    assert f"{MIRROR}.SILVER.thirteenf_holding s" in text["fact_thirteenf_holding"]
    assert list(text)[0] == "master"
    assert "DATEADD(day, 1, day)" in text["dim_date"]


def test_each_object_is_one_dbt_view_that_reads_the_mirror_through_source_and_gold_through_ref():
    models = views.render_models()
    assert set(models) == {f"{item['name']}.sql" for item in views.load()["objects"]}
    assert models["master.sql"].startswith("{{ config(materialized='view') }}")
    assert "{{ source('mdm', 'mastering_master') }}" in models["master.sql"]
    assert "{{ ref('master') }}" in models["dim_company.sql"] and "CREATE" not in models["dim_company.sql"]
    assert "{{ source('silver', 'thirteenf_filing') }}" in models["fact_thirteenf_holding.sql"]


def test_the_dbt_sources_name_the_mirror_database_and_only_the_tables_the_views_read():
    found = {s["name"]: (s["database"], s["schema"], [t["name"] for t in s["tables"]]) for s in views.sources()["sources"]}
    exposed = sorted(t["table"] for t in files.load(files.ROOT.parent / "destination" / "authorised_data_sharing.yaml")["tables"] if t["layer"] == "silver")
    assert found["silver"] == (MIRROR, "SILVER", exposed)   # every exposed silver table has its fact
    assert found["mdm"] == (MIRROR, "MDM", ["mastering_identifier", "mastering_master"])


def test_the_project_is_written_from_the_configuration_and_a_dropped_view_is_dropped(tmp_path):
    (tmp_path / "models").mkdir()
    (tmp_path / "models" / "old_view.sql").write_text("select 1")
    written = views.write_project(tmp_path)
    assert written == sorted(f"{item['name']}.sql" for item in views.load()["objects"])
    assert not (tmp_path / "models" / "old_view.sql").exists()
    assert MIRROR in (tmp_path / "models" / "sources.yml").read_text()


def test_each_database_is_named_once_and_the_committed_dbt_profile_follows_it():
    config = views.load()
    assert config["mirror"]["database"] == MIRROR
    assert "database" not in files.load(views.CONFIG)["mirror"] and "destination" not in files.load(views.CONFIG)
    assert "database" not in files.load(files.ROOT.parent / "destination" / "authorised_data_sharing.yaml")["target"]
    committed = (files.ROOT.parent / "infra" / "dbt" / "gold" / "profiles.yml").read_text()
    assert views.profile(committed) == committed
    assert f"database: {DEST}" in committed
    renamed = views.profile(committed, {"destination": {"database": "RENAMED_GOLD", "schema": "RENAMED"}})
    assert "database: RENAMED_GOLD" in renamed and "schema: RENAMED" in renamed and DEST not in renamed.split("outputs:")[1]


def test_the_exposure_scripts_take_the_mirror_name_from_the_same_file():
    import sys
    sys.path.insert(0, str(files.ROOT.parent / "skills" / "data-platform" / "scripts" / "exposure"))
    import exposure_manifest
    assert exposure_manifest.load_config(files.ROOT.parent / "destination" / "authorised_data_sharing.yaml")["target"]["database"] == MIRROR


def test_the_one_names_file_also_names_the_owner_role():
    assert NAMES["owner"] and set(NAMES) == {"owner", "mirror", "gold"}


def test_each_exposed_silver_table_gets_a_fact_made_from_its_spec_and_an_explicit_object_wins():
    config = views.load()
    facts = {item["source"]: item for item in config["objects"] if item["kind"] == "fact"}
    exposed = {f"silver.{t['table']}" for t in files.load(files.ROOT.parent / "destination" / "authorised_data_sharing.yaml")["tables"] if t["layer"] == "silver"}
    assert exposed <= set(facts)
    nport = facts["silver.nport_holding"]
    assert nport["key"] == ["accession_number", "holding_id"] and nport["requirement"] == "silver_spec"
    assert {(l["role"], l["dimension"]) for l in nport["links"]} == {
        ("fund", "dim_fund_structure"), ("registrant", "dim_company"), ("security", "dim_security")}
    assert nport["times"] == {"business": "period", "event": None, "recorded": "filed"} and "balance" in nport["carry"]
    assert "parent" in facts["silver.thirteenf_holding"]   # the configured 13F fact, not a generated one


def test_a_generated_fact_resolves_its_links_and_dates_on_rows():
    config = views.load()
    item = next(i for i in config["objects"] if i["name"] == "fact_ipo_filing")
    conn = sqlite3.connect(":memory:")
    conn.executescript("""
        create table mastering_master (entity_id text, canonical_id text, kind text, status text, body text);
        create table mastering_identifier (namespace text, value text, entity_id text);
        create table ipo_filing (accession_number text, cik text, form text, stage text, filing_date text,
                                 file_number text, observed_at text);
        create table master_binding (source_code text, source_key text, kind text, master_id text);
    """)
    link = item["links"][0]
    conn.execute("insert into master_binding values (?, '1', 'company', 'c3')", [link["source_code"]])  # a merged-away master
    conn.executemany("insert into mastering_master values (?, ?, ?, ?, ?)", [
        ("c1", "c1", "company", "active", "{}"), ("c3", "c1", "company", "alias", "{}")])
    conn.executemany("insert into ipo_filing values (?,?,?,?,?,?,?)", [
        ("a1", "1", "S-1", "initial", "2026-01-02", "333-1", "2026-01-03"),   # a merged-away id
        ("a2", "2", "S-1", "initial", "2026-01-04", "333-2", "2026-01-05")])  # never mastered
    statements = views.render(dialect="sqlite", qualify=False)
    for name in ("master", item["name"]):
        conn.execute(statements[name])
    rows = conn.execute(f"select accession_number, filer_key, event_date, recorded_date from {item['name']} order by 1").fetchall()
    assert rows == [("a1", "c1", "2026-01-02", "2026-01-03"), ("a2", config["members"]["unknown"], "2026-01-04", "2026-01-05")]


def failing(conn, sql):
    return conn.execute(sql).fetchall()


def test_a_link_that_resolves_less_than_its_inclusion_fails_its_gold_test(db):
    """Operator, 2026-11-22: "gold must have best data quality". The fixture's filing of manager 9 has no master:
    four of five filing rows resolve, under the share of 1.0 a link declares by default."""
    tests = views.quality_tests(dialect="sqlite", qualify=False)
    test = tests["thirteenf_filing_cik_resolves"]
    assert failing(db, test) == [(5, 4)]
    db.execute("insert into master_binding values ('sec.company.v1', '9', 'company', 'c4')")
    assert failing(db, test) == []


def test_a_generated_fact_link_takes_its_inclusion_from_the_silver_spec():
    tests = views.quality_tests(dialect="sqlite", qualify=False)
    assert "WHERE t.found < 1.0 * t.n" in tests["ipo_filing_cik_resolves"]
    assert set(tests) >= {f"{item['source'].split('.')[1]}_{link['column']}_resolves"
                          for item in views.load()["objects"] for link in item.get("links", [])}


def identifier_config():
    config = views.load()
    item = {"name": "fact_offering", "kind": "fact", "source": "silver.offering", "key": ["offering_id"],
            "links": [{"column": "ticker", "kind": "security", "identifier": "ticker", "dimension": "dim_security",
                       "role": "security", "inclusion": 0.5}], "requirement": "silver_spec", "grain": "one row per offering"}
    return {**config, "objects": [o for o in config["objects"] if o["kind"] in ("base", "dimension")] + [item]}


def test_an_identifier_two_masters_hold_fails_its_gold_test_and_finds_no_master(db):
    config = identifier_config()
    db.execute("create table offering (offering_id text, ticker text)")
    db.executemany("insert into offering values (?, ?)", [("o1", "AAA"), ("o2", "BBB")])
    db.executemany("insert into mastering_identifier values (?, ?, ?)", [("ticker", "AAA", "s1"), ("ticker", "BBB", "s2")])
    db.execute(views.render(config, dialect="sqlite", qualify=False)["fact_offering"])
    tests = views.quality_tests(config, dialect="sqlite", qualify=False)
    assert failing(db, tests["security_ticker_one_master"]) == []
    assert failing(db, tests["offering_ticker_resolves"]) == []
    db.execute("insert into mastering_identifier values ('ticker', 'BBB', 's1')")   # a second master holds BBB
    assert failing(db, tests["security_ticker_one_master"]) == [("BBB",)]
    assert rows(db, "select offering_id, security_key from fact_offering order by 1") == [("o1", "s1"), ("o2", "unknown")]
    db.execute("insert into mastering_identifier values ('ticker', 'AAA', 's2')")   # now neither resolves: 0 of 2 < 0.5
    assert failing(db, tests["offering_ticker_resolves"]) == [(2, 0)]


def test_the_project_writes_one_dbt_test_per_rule(tmp_path):
    views.write_project(tmp_path)
    written = sorted(p.name for p in (tmp_path / "tests").glob("*.sql"))
    assert written == sorted(f"{name}.sql" for name in views.quality_tests())
    assert "{{ source('silver', 'master_binding') }}" in (tmp_path / "tests" / "thirteenf_filing_cik_resolves.sql").read_text()


def test_rdm_publishes_one_view_per_published_code_set():
    views_by_set = {i["code_set"]: i["name"] for i in views.load()["objects"] if i["kind"] == "code_set"}
    published = sorted(d.name for d in (files.ROOT / "reference" / "published").iterdir() if d.is_dir())
    assert sorted(views_by_set) == published
    assert views_by_set["sec-place-types"] == "ref_sec_place_types"


def test_every_published_code_set_holds_exactly_one_version():
    folders = [d for d in (files.ROOT / "reference" / "published").iterdir() if d.is_dir()]
    assert {d.name: len([v for v in d.iterdir() if v.is_dir()]) for d in folders} == {d.name: 1 for d in folders}


def test_a_code_set_view_selects_its_one_version_by_name():
    config = views.load()
    item = next(i for i in config["objects"] if i["name"] == "ref_sec_place_types")
    conn = sqlite3.connect(":memory:")
    conn.execute(f"create table published_code (code_set text, {', '.join(item['columns'])})")
    rest = [c for c in item["columns"] if c not in ("code", "label", "version")]
    conn.executemany(f"insert into published_code (code_set, code, label, version, {', '.join(rest)}) "
                     f"values (?, ?, ?, ?, {', '.join('?' * len(rest))})", [
        ("sec-place-types", "A", "Kept", item["version"], *[None] * len(rest)),
        ("sec-place-types", "A", "Left over", "an-older-version", *[None] * len(rest)),   # a stale row never reaches it
        ("another-set", "Z", "Other", item["version"], *[None] * len(rest))])
    conn.execute(views.render(dialect="sqlite", qualify=False)[item["name"]])
    assert conn.execute(f"select code, label from {item['name']}").fetchall() == [("A", "Kept")]


def test_a_code_set_with_two_versions_is_refused(tmp_path, monkeypatch):
    for version in ("1", "2"):
        (tmp_path / "reference" / "published" / "invented-set" / version).mkdir(parents=True)
    monkeypatch.setattr(views.files, "ROOT", tmp_path)
    with pytest.raises(ValueError, match="invented-set holds 2 versions"):
        views.code_set_views({"code_sets": {"published": "reference/published", "name": "ref_{code_set}", "source": "rdm.x",
                                            "columns": ["code"], "requirement": "r"}})


def test_the_gold_configuration_is_a_destination_not_a_rule():
    """Operator, 2026-11-21: "move rules/gold to destination/gold": where Gold is written is not a rule."""
    root = files.ROOT.parent
    assert views.CONFIG == root / "destination" / "gold" / "gold.yaml" and views.CONFIG.is_file()
    assert not (files.ROOT / "gold").exists()
