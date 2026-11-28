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


def body(entity, kind, name, canonical=None, status="active", listings=()):
    return json.dumps({"entity_id": entity, "canonical_id": canonical or entity, "kind": kind, "status": status,
                       "fields": {"name": {"value": name}}, "details": {"listings": [dict(l) for l in listings]}})


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
        create table set_aside (namespace text, value text, source_code text, reason text, probable_kind text);
    """)
    published(conn)
    masters = [("c1", body("c1", "company", "Alpha Capital")), ("c2", body("c2", "company", "Beta Partners")),
               ("c3", body("c3", "company", "Alpha Cap Old", canonical="c1", status="alias")),
               ("c4", body("c4", "company", "Delta Fund")),
               ("s1", body("s1", "security", "Alpha Common")), ("s2", body("s2", "security", "Beta Notes"))]
    conn.executemany("insert into mastering_master values (?, ?, ?, ?, ?)",  # the columns, and the body that holds the name
                     [(e, b["canonical_id"], b["kind"], b["status"], json.dumps({"fields": b["fields"], "details": b["details"]})) for e, b in
                      ((e, json.loads(text)) for e, text in masters)])
    conn.executemany("insert into mastering_identifier values (?, ?, ?)",
                     [("cik", "0000000001", "c1"), ("cik", "0000000002", "c2"), ("cik", "0000000003", "c3"),
                      ("cusip", "AAA111", "s1")])
    conn.executemany("insert into thirteenf_filing values (?,?,?,?,?,?)", [
        ("f1", "0000000001", "13F-HR", "2026-02-10", "2025-12-31", "a.xml"),
        ("f2", "0000000001", "13F-HR", "2026-02-11", "2025-12-31", "b.xml"),  # a joint filing: two managers
        ("f2", "0000000002", "13F-HR", "2026-02-11", "2025-12-31", "b.xml"),
        ("f3", "0000000009", "13F-NT", "2026-02-12", "2025-12-31", "c.xml"),   # a manager that was never mastered
        ("f4", "0000000003", "13F-HR", "2026-02-13", "2025-12-31", "d.xml")])  # held by a master that merged away
    conn.executemany("insert into thirteenf_holding values (?,?,?,?,?,?,?,?,?,?,?)", [
        ("f1", 1, "AAA111", 100, "SH", 1000.5, None, "SOLE", 100, 0, 0),
        ("f1", 2, "BBB222", 50, "SH", 250.25, None, "SOLE", 50, 0, 0),
        ("f2", 1, "AAA111", 10, "SH", 99.0, "Call", "SOLE", 10, 0, 0),
        ("f3", 1, "ZZZ999", 5, "PRN", 5.0, None, "SOLE", 5, 0, 0),   # no master security
        ("f4", 1, "AAA111", 7, "SH", 70.0, None, "SOLE", 7, 0, 0)])
    conn.executemany("insert into master_binding values (?,?,?,?)", [
        ("sec.thirteenf.securities.v2", "AAA111", "security", "s1"),
        ("sec.thirteenf.securities.v2", "BBB222", "security", "s2")])
    for statement in views.render(dialect="sqlite", qualify=False).values():
        conn.execute(statement)
    return conn


def rows(conn, sql):
    return conn.execute(sql).fetchall()


def code(code_set, code, crosswalk=(), parent_code=None, level=None):
    return {"code_set": code_set, "code": code,   # a crosswalk entry as RDM publishes it
            "crosswalk": json.dumps([dict(zip(("to_set", "to_version", "to_code", "match_type"), c)) for c in crosswalk]),
            "parent_code": parent_code, "level": level}


def published(conn):
    """The two published code sets a ticker's venue reads, each at the version its Gold view selects."""
    config = views.load()
    sets = {i["code_set"]: i for i in config["objects"] if i["kind"] == "code_set"}
    columns = config["code_sets"]["columns"]
    conn.execute(f"create table published_code (code_set text, {', '.join(columns)})")
    for row in (code("sec-cover-exchange", "NASDAQ CAPITAL MARKET", [("another-set", "1", "XNSE", "exact"),
                                                                     ("iso-10383-mic", "1", "XNCM", "exact")]),
                code("sec-cover-exchange", "NASDAQ GLOBAL SELECT MARKET", [("iso-10383-mic", "1", "XNGS", "exact")]),
                code("sec-cover-exchange", "NYSE", [("iso-10383-mic", "1", "XNYS", "exact")]),
                code("iso-10383-mic", "XNAS", level="Operating MIC"),
                code("iso-10383-mic", "XNYS", level="Operating MIC"),
                code("iso-10383-mic", "XNCM", parent_code="XNAS", level="Market segment MIC"),
                code("iso-10383-mic", "XNGS", parent_code="XNAS", level="Market segment MIC"),
                code("iso-10383-mic", "XNSE", level="Operating MIC")):
        row["version"] = sets[row["code_set"]]["version"]
        conn.execute(f"insert into published_code ({', '.join(row)}) values ({', '.join('?' * len(row))})", list(row.values()))


def test_every_object_names_its_requirement_and_every_link_names_a_dimension_that_exists():
    config = views.load()
    names = {item["name"] for item in config["objects"]}
    for item in config["objects"]:
        assert config["requirements"][item["requirement"]] and item["grain"], item["name"]
        for link in item.get("links", []) + ([item["parent"]["single_link"]] if "parent" in item else []):
            assert link["dimensions"] and set(link["dimensions"]) <= names


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
    assert NAMES["owner"] and set(NAMES) == {"owner", "mirror", "gold", "operations"}


def test_each_exposed_silver_table_gets_a_fact_made_from_its_spec_and_an_explicit_object_wins():
    config = views.load()
    facts = {item["source"]: item for item in config["objects"] if item["kind"] == "fact"}
    exposed = {f"silver.{t['table']}" for t in files.load(files.ROOT.parent / "destination" / "authorised_data_sharing.yaml")["tables"] if t["layer"] == "silver"}
    assert exposed <= set(facts)
    nport = facts["silver.nport_holding"]
    assert nport["key"] == ["accession_number", "holding_id"] and nport["requirement"] == "silver_spec"
    assert {(l["role"], *l["dimensions"]) for l in nport["links"]} == {
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
    conn.execute("insert into mastering_identifier values (?, '0000000001', 'c3')", [link["identifier"]])  # a merged-away master
    conn.executemany("insert into mastering_master values (?, ?, ?, ?, ?)", [
        ("c1", "c1", "company", "active", "{}"), ("c3", "c1", "company", "alias", "{}")])
    conn.executemany("insert into ipo_filing values (?,?,?,?,?,?,?)", [
        ("a1", "0000000001", "S-1", "initial", "2026-01-02", "333-1", "2026-01-03"),   # a merged-away id
        ("a2", "0000000002", "S-1", "initial", "2026-01-04", "333-2", "2026-01-05")])  # never mastered
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
    db.execute("insert into mastering_identifier values ('cik', '0000000009', 'c4')")
    assert failing(db, test) == []


def test_a_generated_fact_link_takes_its_inclusion_from_the_silver_spec():
    tests = views.quality_tests(dialect="sqlite", qualify=False)
    assert "WHERE t.found < 1.0 * t.n" in tests["ipo_filing_cik_resolves"]
    assert set(tests) >= {f"{item['source'].split('.')[1]}_{link['column']}_resolves"
                          for item in views.load()["objects"] for link in item.get("links", [])}


def identifier_config():
    config = views.load()
    item = {"name": "fact_offering", "kind": "fact", "source": "silver.offering", "key": ["offering_id"],
            "links": [{"column": "ticker", "kinds": ["security"], "identifier": "ticker", "dimensions": ["dim_security"],
                       "role": "security", "inclusion": 0.5}], "requirement": "silver_spec", "grain": "one row per offering"}
    return {**config, "objects": [o for o in config["objects"] if o["kind"] in ("base", "dimension")] + [item]}


def test_an_identifier_two_masters_hold_fails_its_gold_test_and_finds_no_master(db):
    config = identifier_config()
    db.execute("create table offering (offering_id text, ticker text)")
    db.executemany("insert into offering values (?, ?)", [("o1", "AAA"), ("o2", "BBB")])
    db.executemany("insert into mastering_identifier values (?, ?, ?)", [("ticker", "AAA", "s1"), ("ticker", "BBB", "s2")])
    db.execute(views.render(config, dialect="sqlite", qualify=False)["fact_offering"])
    tests = views.quality_tests(config, dialect="sqlite", qualify=False)
    assert failing(db, tests["offering_ticker_one_master"]) == []
    assert failing(db, tests["offering_ticker_resolves"]) == []
    db.execute("insert into mastering_identifier values ('ticker', 'BBB', 's1')")   # a second master holds BBB
    assert failing(db, tests["offering_ticker_one_master"]) == [("BBB",)]
    assert rows(db, "select offering_id, security_key from fact_offering order by 1") == [("o1", "s1"), ("o2", "unknown")]
    db.execute("insert into mastering_identifier values ('ticker', 'AAA', 's2')")   # now neither resolves: 0 of 2 < 0.5
    assert failing(db, tests["offering_ticker_resolves"]) == [(2, 0)]


def test_two_tables_reading_one_identifier_each_get_their_test():
    names = set(views.quality_tests(dialect="sqlite", qualify=False))
    assert {"registration_offering_cik_one_master", "prospectus_offering_cik_one_master"} <= names


def test_a_source_key_bound_to_two_masters_fails_its_gold_test(db):
    test = views.quality_tests(dialect="sqlite", qualify=False)["master_binding_one_master_per_key"]
    assert failing(db, test) == []
    db.execute("insert into master_binding values ('sec.thirteenf.securities.v2', 'AAA111', 'security', 's2')")
    assert failing(db, test) == [("sec.thirteenf.securities.v2", "AAA111")]


def test_the_project_writes_one_dbt_test_per_rule(tmp_path):
    views.write_project(tmp_path)
    written = sorted(p.name for p in (tmp_path / "tests").glob("*.sql"))
    assert written == sorted(f"{name}.sql" for name in views.quality_tests())
    written = (tmp_path / "tests" / "thirteenf_filing_cik_resolves.sql").read_text()
    assert "{{ source('mdm', 'mastering_identifier') }}" in written and "{{ source('silver', 'set_aside') }}" in written


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


def test_a_silver_column_named_like_its_dimension_key_is_carried_under_the_source_key_name():
    """The silver row's own key of a master can share the dimension key's name: the fact keeps both, the source's value
    under the configured source-key name."""
    config = views.load()
    rule = config["silver_facts"]
    item = next(i for i in config["objects"] if i["name"] == "fact_company_fact")
    link = next(l for l in item["links"] if rule["dimension_key"].format(role=l["role"]) in item["key"] + item["carry"])
    column, dimension_key = link["column"], rule["dimension_key"].format(role=link["role"])
    columns = list(dict.fromkeys([*item["key"], *[c for c in item["times"].values() if c], *item["carry"]]))
    conn = sqlite3.connect(":memory:")
    conn.executescript("""
        create table mastering_master (entity_id text, canonical_id text, kind text, status text, body text);
        create table mastering_identifier (namespace text, value text, entity_id text);
        create table master_binding (source_code text, source_key text, kind text, master_id text);
    """)
    conn.execute(f"create table company_fact ({', '.join(chr(34) + c + chr(34) + ' text' for c in columns)})")
    conn.execute(f"insert into company_fact ({', '.join(chr(34) + c + chr(34) for c in columns)}) values ({', '.join('?' for _ in columns)})",
                 [("0000000001" if c == column else f"invented-{c}") for c in columns])
    conn.execute("insert into mastering_identifier values (?, '0000000001', 'c1')", [link["identifier"]])
    conn.execute("insert into mastering_master values ('c1', 'c1', 'company', 'active', '{}')")
    statements = views.render(dialect="sqlite", qualify=False)
    for name in ("master", item["name"]):
        conn.execute(statements[name])
    found = conn.execute(f"select * from {item['name']}")
    names = [d[0] for d in found.description]
    row = dict(zip(names, found.fetchone()))
    assert len(names) == len(set(names))
    assert row[dimension_key] == "c1" and row[rule["source_key"].format(role=link["role"])] == "0000000001"


def test_the_snowflake_column_name_is_quoted_in_the_mirrors_case():
    assert views.DIALECTS["snowflake"]["column"]("row") == '"ROW"'


def test_a_configured_fact_carries_a_column_of_its_dimension_keys_name_under_the_source_key_name_too():
    config = views.load()
    ctx = views.Context(config, "sqlite", qualify=False)
    rule = config["silver_facts"]
    link = {"role": "manager", "column": "cik", "source_code": "invented.v1", "kind": "company"}
    item = {"key": ["accession_number"], "links": [], "carry": [rule["dimension_key"].format(role="manager"), "form"],
            "parent": {"single_link": link}}
    assert ctx.source_names(item) == {rule["dimension_key"].format(role="manager"): rule["source_key"].format(role="manager")}


def offering_config(link: dict) -> dict:
    """The Gold configuration with one invented offering fact holding `link`."""
    config = views.load()
    item = {"name": "fact_offering", "kind": "fact", "source": "silver.offering", "key": ["offering_id"],
            "links": [{"column": "ticker", "role": "listed_security", **link}], "requirement": "silver_spec",
            "grain": "one row per offering"}
    keep = [o for o in config["objects"] if o["kind"] in ("base", "dimension", "code_set", "detail")]
    return {**config, "objects": keep + [item]}


def offering(db, config, offerings):
    db.execute("create table offering (offering_id text, ticker text, exchange text)")
    db.executemany("insert into offering values (?, ?, ?)", offerings)
    db.execute(views.render(config, dialect="sqlite", qualify=False)["fact_offering"])
    return views.quality_tests(config, dialect="sqlite", qualify=False)


def add_masters(db, masters, identifiers):
    db.executemany("insert into mastering_master values (?, ?, ?, ?, ?)",
                   [(e, canonical or e, kind, "active", json.dumps({"fields": {}, "details": {"listings": listings}}))
                    for e, canonical, kind, listings in masters])
    db.executemany("insert into mastering_identifier values (?, ?, ?)", identifiers)


def test_a_cik_link_finds_its_master_by_the_identifier_whichever_feed_mastered_it(db):
    """Operator, 2026-11-27 (company phase 2, decision 7): a Gold link resolves by its identifier on any master of its
    kinds. The fixture binds no company's source key: every filing finds its manager by the CIK the master holds."""
    assert rows(db, "select count(*) from master_binding where source_code = 'sec.company.v1'") == [(0,)]
    got = rows(db, "select accession_number, cik, manager_key from fact_thirteenf_filing order by 1, 2")
    assert got == [("f1", "0000000001", "c1"), ("f2", "0000000001", "c1"), ("f2", "0000000002", "c2"),
                   ("f3", "0000000009", "unknown"), ("f4", "0000000003", "c1")]


def test_an_identifier_an_alias_and_its_survivor_hold_is_one_master(db):
    config = offering_config({"kinds": ["security"], "identifier": "ticker", "dimensions": ["dim_security"]})
    add_masters(db, [("s9", "s1", "security", [])], [("ticker", "AAA", "s1"), ("ticker", "AAA", "s9")])
    tests = offering(db, config, [("o1", "AAA", None)])
    assert rows(db, "select listed_security_key from fact_offering") == [("s1",)]
    assert failing(db, tests["offering_ticker_one_master"]) == [] and failing(db, tests["offering_ticker_resolves"]) == []


def test_a_link_of_several_kinds_finds_a_master_of_any_and_fails_on_two(db):
    """Decision 9: a reporting owner is a person or a company, by CIK."""
    config = offering_config({"kinds": ["person", "company"], "identifier": "cik",
                              "dimensions": ["dim_person", "dim_company"]})
    add_masters(db, [("p1", None, "person", []), ("p2", None, "person", [])],
                [("cik", "0000000005", "p1"), ("cik", "0000000002", "p2")])
    tests = offering(db, config, [("o1", "0000000005", None), ("o2", "0000000001", None), ("o3", "0000000002", None)])
    assert dict(rows(db, "select offering_id, listed_security_key from fact_offering")) == {
        "o1": "p1", "o2": "c1", "o3": "unknown"}   # the CIK of a person and a company resolves to neither
    assert failing(db, tests["offering_ticker_one_master"]) == [("0000000002",)]


def test_a_key_the_set_aside_table_holds_is_out_of_its_links_test(db):
    """Decision 10: a key a classification rule held back is out of scope; every other key resolves."""
    test = views.quality_tests(dialect="sqlite", qualify=False)["thirteenf_filing_cik_resolves"]
    assert failing(db, test) == [(5, 4)]
    db.execute("insert into set_aside values ('cik', '0000000009', 'sec.company.v1', 'classification_deferred', 'fund_structure')")
    assert failing(db, test) == []
    db.execute("delete from set_aside")
    db.execute("insert into set_aside values ('ticker', '0000000009', 'sec.company.v1', 'classification_deferred', null)")
    assert failing(db, test) == [(5, 4)]   # another namespace's value is another key


VENUE = {"kinds": ["security"], "identifier": "ticker", "venue": "exchange", "dimensions": ["dim_security"]}


def test_a_ticker_several_securities_hold_resolves_by_the_covers_operating_mic_then_the_us_isin(db):
    """Decisions 12 and 13: among the Securities holding the ticker, the one listed on the cover's operating MIC; of
    several there, the one with a US ISIN. A segment MIC counts as its operating MIC on both sides."""
    add_masters(db, [("s7", None, "security", [{"ticker": "GP", "mic": "XNCM"}, {"ticker": "GP", "mic": "XNYS"}]),
                     ("s8", None, "security", [{"ticker": "GP", "mic": "XNSE"}]),
                     ("s5", None, "security", [{"ticker": "SGP", "mic": "XNGS"}]),
                     ("s6", None, "security", [{"ticker": "SGP", "mic": "XNCM"}])],
                [("ticker", "GP", "s7"), ("ticker", "GP", "s8"), ("ticker", "SGP", "s5"), ("ticker", "SGP", "s6"),
                 ("isin", "US0000000005", "s5"), ("isin", "PH0000000006", "s6"), ("ticker", "ONE", "s1")])
    tests = offering(db, offering_config(VENUE), [
        ("o1", "GP", " Nasdaq Capital Market"), ("o2", "SGP", "NASDAQ Global Select Market"), ("o3", "ONE", None)])
    assert dict(rows(db, "select offering_id, listed_security_key from fact_offering")) == {"o1": "s7", "o2": "s5", "o3": "s1"}
    assert failing(db, tests["offering_ticker_resolves"]) == []


def test_a_shared_ticker_whose_cover_names_no_mapped_exchange_is_out_of_the_test_as_exchange_not_mapped(db):
    add_masters(db, [("s7", None, "security", [{"ticker": "GP", "mic": "XNCM"}]),
                     ("s8", None, "security", [{"ticker": "GP", "mic": "XNSE"}])],
                [("ticker", "GP", "s7"), ("ticker", "GP", "s8"), ("ticker", "ONE", "s1")])
    tests = offering(db, offering_config(VENUE), [("o1", "GP", "Invented Exchange"), ("o2", "GP", None),
                                                  ("o3", "ONE", "Invented Exchange")])
    assert dict(rows(db, "select offering_id, listed_security_key from fact_offering")) == {
        "o1": "unknown", "o2": "unknown", "o3": "s1"}   # a ticker one Security holds needs no exchange
    assert failing(db, tests["offering_ticker_resolves"]) == []
    db.execute("insert into offering values ('o4', 'GP', 'NYSE')")   # mapped, and neither holder is listed there
    assert failing(db, tests["offering_ticker_resolves"]) == [(2, 1)]


def test_a_securitys_listings_are_one_gold_row_each_with_their_mic(db):
    add_masters(db, [("s7", None, "security", [{"ticker": "GP", "mic": "XNCM", "exchange": "UR"}, {"ticker": "GP"}])], [])
    assert rows(db, "select entity_id, ticker, exchange, mic from security_listing where entity_id = 's7' order by mic") == [
        ("s7", "GP", None, None), ("s7", "GP", "UR", "XNCM")]


def test_a_listing_kept_on_a_master_that_merged_away_counts_for_the_master_it_became(db):
    add_masters(db, [("s7", None, "security", []), ("s3", "s7", "security", [{"ticker": "GP", "mic": "XNCM"}]),
                     ("s8", None, "security", [{"ticker": "GP", "mic": "XNSE"}])],
                [("ticker", "GP", "s7"), ("ticker", "GP", "s8")])
    offering(db, offering_config(VENUE), [("o1", "GP", "Nasdaq Capital Market")])
    assert rows(db, "select listed_security_key from fact_offering") == [("s7",)]
