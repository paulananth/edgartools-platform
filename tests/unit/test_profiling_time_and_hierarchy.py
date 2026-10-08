"""Time roles and hierarchies of the data-profiling skill, on small tables."""

import sys
from pathlib import Path

import pytest

duckdb = pytest.importorskip("duckdb")  # in the mdm extra, which CI installs

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "skills" / "data-profiling" / "scripts"))
from profiling import hierarchy, profile, timing  # noqa: E402


@pytest.fixture
def con():
    return duckdb.connect()


def test_valid_pair_needs_start_and_end_words_and_order(con):
    con.execute("""CREATE TABLE t AS SELECT i AS k, DATE '2020-01-01' + CAST(i AS INTEGER) AS valid_from,
                   CASE WHEN i % 2 = 0 THEN NULL ELSE DATE '2021-01-01' + CAST(i AS INTEGER) END AS valid_to,
                   DATE '2019-01-01' + CAST(i AS INTEGER) AS shipped_on FROM range(100) r(i)""")
    roles = timing.roles(con, "t", profile.columns(con, "t"), ["k"])
    assert roles["as_of"] == {"from": "valid_from", "to": "valid_to"}
    assert roles["event_time"] == "shipped_on"


def test_record_time_and_personal_dates(con):
    con.execute("""CREATE TABLE t AS SELECT i AS k, DATE '1980-01-01' + CAST(i AS INTEGER) AS birth_date,
                   TIMESTAMP '2025-01-01 00:00:00' + INTERVAL (i) MINUTE AS last_updated FROM range(10) r(i)""")
    roles = timing.roles(con, "t", profile.columns(con, "t"), ["k"], personal={"birth_date"})
    assert roles["as_at"] == "last_updated" and roles["event_time"] is None


def test_daily_series_with_its_step_and_gaps(con):
    con.execute("""CREATE TABLE t AS SELECT DATE '2025-01-01' + CAST(d AS INTEGER) AS day, c AS code, d * 1.5 AS rate
                   FROM range(30) a(d), (VALUES ('A'), ('B')) b(c) WHERE NOT (c = 'B' AND d = 10)""")
    s = timing.roles(con, "t", profile.columns(con, "t"), ["day", "code"])["series"]
    assert s["key"] == ["code"] and s["time"] == "day" and s["step"].startswith("1 day") and s["gaps"] == 1


def test_parent_column_depth_orphans_and_cycles(con):
    con.execute("""CREATE TABLE t (node VARCHAR, up VARCHAR);
                   INSERT INTO t VALUES ('a', NULL), ('b', 'a'), ('c', 'b'), ('d', 'a'), ('e', 'zz'),
                                        ('x', 'y'), ('y', 'x')""")
    h = hierarchy.by_parent_column(con, "t", "up", "node")
    assert h["depth"] == 3 and h["orphans"] == 1 and h["cycles"] == 2 and h["shape"] == "ragged"


def test_link_part_gives_one_hierarchy_per_role_with_one_parent(con):
    con.execute("""CREATE TABLE l (child VARCHAR, parent VARCHAR, kind VARCHAR);
                   INSERT INTO l VALUES ('b', 'a', 'owns'), ('c', 'b', 'owns'), ('d', 'a', 'owns'),
                                        ('b', 'x', 'knows'), ('b', 'y', 'knows')""")
    found = hierarchy.by_link_part(con, "l", "child", "parent", "kind")
    assert [h["role"] for h in found] == ["owns"]  # "knows" has two parents for b: a network
    assert found[0]["depth"] == 3 and found[0]["evidence_kind"] == "parent_column"


def test_a_node_that_names_itself_as_parent_is_marked_apart_from_a_cycle(con):
    con.execute("CREATE TABLE selfish AS SELECT * FROM (VALUES ('a', 'b', 'r'), ('b', 'a', 'r'), ('c', 'c', 'r'), "
                "('d', 'a', 'r')) t(child, parent, kind)")
    h, = hierarchy.by_link_part(con, "selfish", "child", "parent", "kind", ["child", "kind"])
    reasons = sorted((m["value"], m["reason"]) for m in h["marked"])
    assert reasons == [("a", "on a cycle of parents"), ("b", "on a cycle of parents"), ("c", "names itself as its parent")]
    assert h["cycles"] == 3 and h["invalid_rows"] == 3 and all(m["needs_steward"] for m in h["marked"])


def test_a_row_breaking_two_levels_is_one_invalid_row_with_counted_evidence(con):
    rows = [(f"r{n}", f"c{n % 6}", f"m{n % 6 // 2}", f"t{n % 6 // 4}") for n in range(60)]
    rows.append(("bad", "c0", "m2", "t9"))  # breaks fine → middle and middle → top
    con.execute("CREATE TABLE levels (row_id VARCHAR, fine VARCHAR, middle VARCHAR, top VARCHAR)")
    con.executemany("INSERT INTO levels VALUES (?, ?, ?, ?)", rows)
    h = hierarchy._record(con, "levels", ["fine", "middle", "top"], 0.99, "functional_dependency", ["row_id"])
    assert h["invalid_rows"] == 1 and [m["key"] for m in h["marked"]] == [{"row_id": "bad"}]
    m, = h["marked"]
    assert m["fix"] == "m0" and m["support"] == {"rows": 10, "of": 11} and m["parent_column"] == "middle"


def test_a_child_part_marks_its_rows_by_its_parent_row(con):
    rows = [(n // 10, f"r{n}", f"c{n % 6}", f"m{n % 6 // 2}") for n in range(60)]
    rows.append((9, "bad", "c0", "m2"))
    con.execute("CREATE TABLE child (_parent_row BIGINT, line VARCHAR, fine VARCHAR, middle VARCHAR)")
    con.executemany("INSERT INTO child VALUES (?, ?, ?, ?)", rows)
    h = hierarchy._record(con, "child", ["fine", "middle"], 0.99, "functional_dependency", ["parent_id", "line"])
    assert [m["key"] for m in h["marked"]] == [{"_parent_row": "9", "line": "bad"}]


def test_a_dependency_that_holds_by_coincidence_is_not_a_hierarchy():
    import duckdb
    from profiling import hierarchy, profile

    con = duckdb.connect()
    # region → country is real; a flag set on 99% of rows is "determined" by anything; a building number
    # seen on one row each determines its country trivially.
    con.execute("""CREATE TABLE t AS SELECT
        'R' || (i % 40) AS region, 'C' || (i % 40 % 8) AS country,
        CASE WHEN i < 990 THEN 'Y' ELSE 'N' END AS flag,
        CASE WHEN i < 990 THEN 'Q' || (i % 30) ELSE 'Q' || (i % 30) END AS quarter,
        'B' || i AS building
        FROM range(1000) r(i)""")
    columns = {c["name"]: c for c in profile.columns(con, "t")}
    rejected = []
    found = hierarchy.by_dependency(con, "t", [columns["region"], columns["country"]], ["building"], rejected)
    assert [h["levels"][-1]["column"] for h in found] == ["region"] and not rejected
    rejected = []
    assert hierarchy.by_dependency(con, "t", [columns["quarter"], columns["flag"]], ["building"], rejected) == []
    (flag,) = rejected
    assert (flag["child"], flag["parent"]) == ("quarter", "flag") and flag["lift"] < hierarchy.LIFT
    evidence = hierarchy.chance(con, "t", "building", "country", 1.0)
    assert evidence["supported"] == 0 and hierarchy.coincidental(evidence)


def test_a_list_of_codes_keeps_its_finest_level_and_a_skewed_level_is_not_skipped():
    import duckdb
    from profiling import hierarchy, profile

    con = duckdb.connect()
    # One row per city: city → region → country, region skewed (most cities in R0), a few dirty rows.
    con.execute("""CREATE TABLE geo AS SELECT 'C' || i AS city,
        CASE WHEN i % 20 = 0 THEN 'R' || (i % 7 + 1) ELSE 'R0' END AS region,
        CASE WHEN i % 20 = 0 THEN 'K' || ((i % 7 + 1) % 3 + 1) ELSE 'K0' END AS country
        FROM range(2000) r(i)""")
    con.execute("UPDATE geo SET country = 'K9' WHERE city IN ('C1', 'C2', 'C3')")  # dirty: region R0 is in K0
    cols = {c["name"]: c for c in profile.columns(con, "geo")}
    rejected = []
    found = hierarchy.by_dependency(con, "geo", [cols["city"], cols["region"], cols["country"]], ["city"],
                                    rejected, list_of_codes=True)
    assert [l["column"] for l in found[0]["levels"]] == ["country", "region", "city"] and not rejected
    assert found[0]["invalid_rows"] == 3  # the dirty rows of a skewed but real level are marked


def test_a_flag_is_never_a_level_and_the_code_finds_its_real_parent():
    import duckdb
    from profiling import hierarchy, profile

    con = duckdb.connect()
    # form → its group (a real level); the group decides a 0/1 flag (never a level); domestic/foreign is a level.
    con.execute("""CREATE TABLE f AS SELECT 'F' || (i % 30) AS form, 'G' || (i % 30 % 6) AS grp,
        CASE WHEN i % 30 % 2 = 0 THEN 1 ELSE 0 END AS numeric_flag,
        CASE WHEN i % 30 % 6 < 3 THEN 'DOMESTIC' ELSE 'FOREIGN' END AS place
        FROM range(3000) r(i)""")
    cols = {c["name"]: c for c in profile.columns(con, "f")}
    assert hierarchy.is_flag(cols["numeric_flag"]) and not hierarchy.is_flag(cols["place"])
    rejected = []
    found = hierarchy.by_dependency(con, "f", [cols["form"], cols["numeric_flag"], cols["grp"], cols["place"]],
                                    ["form"], rejected)
    assert [l["column"] for l in found[0]["levels"]] == ["place", "grp", "form"]
    (flag,) = rejected
    assert (flag["child"], flag["parent"], flag["reason"]) == ("grp", "numeric_flag", "flag")


def test_level_tables_form_a_reference_hierarchy(tmp_path):
    import csv
    import random

    from profiling import run

    rng = random.Random(3)
    folder = tmp_path / "set"
    folder.mkdir()

    def write(name, header, rows):
        with (folder / name).open("w", newline="") as f:
            csv.writer(f).writerows([header, *rows])

    write("division.csv", ["division_code", "division_label"], [[f"D{d}", f"Division {d}"] for d in range(1, 11)])
    write("group.csv", ["group_code", "group_label", "division_code"],
          [[f"G{g:03d}", f"Group {g}", f"D{g % 10 + 1}"] for g in range(1, 151)] + [["G999", "Group 999", "D99"]])
    write("product.csv", ["product_id", "product_name", "group_code", "price"],
          [[f"P{n:05d}", f"Product {n} {rng.choice(['red', 'blue', 'large', 'small'])}", f"G{rng.randint(1, 150):03d}",
            round(rng.uniform(1, 90), 2)] for n in range(1, 1501)])
    write("sale.csv", ["sale_id", "product_id", "sold_on", "qty"],
          [[n, f"P{rng.randint(1, 1500):05d}", f"2025-{rng.randint(1, 12):02d}-{rng.randint(1, 28):02d}",
            rng.randint(1, 9)] for n in range(1, 6001)])
    findings = run.profile_inputs({"set": str(folder)}, "levels")
    classes = {p["part"]: p["class"] for p in findings["parts"]}
    assert classes["group"] == "reference" and classes["division"] == "reference"
    (h,) = [h for h in findings["hierarchies"] if h["evidence_kind"] == "level_tables"]
    assert h["hierarchy"] == "division > group" and h["type"] == "reference" and h["depth"] == 2
    assert [l["column"] for l in h["levels"]] == ["division.division_code", "group.group_code"]
    (orphan,) = [m for m in findings["marked_rows"] if m["hierarchy"] == h["hierarchy"]]
    assert orphan["value"] == "D99" and orphan["fix"] is None and orphan["needs_steward"]  # no division D99


def test_a_counter_key_inside_another_counter_key_is_no_link(tmp_path):
    import csv

    from profiling import run

    folder = tmp_path / "set"
    folder.mkdir()
    with (folder / "kind.csv").open("w", newline="") as f:
        csv.writer(f).writerows([["kind_id", "kind_label"], *[[k, f"Kind {k}"] for k in range(1, 5)]])
    with (folder / "thing.csv").open("w", newline="") as f:
        csv.writer(f).writerows([["thing_id", "thing_name", "kind_id"],
                                 *[[t, f"Thing number {t} of many", t % 4 + 1] for t in range(1, 301)]])
    links = {(r["from"]["part"], r["from"]["columns"][0], r["to"]["part"])
             for r in run.profile_inputs({"set": str(folder)}, "counters")["relationships"]}
    assert ("thing", "kind_id", "kind") in links
    assert not any(a == "kind" for a, _, _ in links)  # kind ids 1..4 are not thing ids


def test_level_tables_need_one_parent_per_level_and_a_list_of_codes(tmp_path):
    import csv

    from profiling import run

    folder = tmp_path / "set"
    folder.mkdir()

    def write(name, header, rows):
        with (folder / name).open("w", newline="") as f:
            csv.writer(f).writerows([header, *rows])

    # A list naming one parent list twice: no chain, and no crash.
    write("region.csv", ["region_code", "region_label"], [[f"R{r}", f"Region {r}"] for r in range(1, 11)])
    write("area.csv", ["area_code", "area_label", "home_region_code", "sales_region_code"],
          [[f"A{a:03d}", f"Area {a}", f"R{a % 10 + 1}", f"R{(a + 3) % 10 + 1}"] for a in range(1, 151)])
    # Free-text notes pointing at a smaller part are not a list of codes.
    write("visit.csv", ["visit_code", "visit_label"], [[f"V{v:03d}", f"Visit {v}"] for v in range(1, 301)])
    write("note.csv", ["note_code", "note_text", "visit_code"],
          [[f"N{n:04d}", f"note {n} about the visit, written at length by the person who saw it", f"V{n % 300 + 1:03d}"]
           for n in range(1, 2001)])
    findings = run.profile_inputs({"set": str(folder)}, "branches")
    assert not [h for h in findings["hierarchies"] if h["evidence_kind"] == "level_tables"]
    assert {p["part"]: p["class"] for p in findings["parts"]}["note"] != "reference"


def test_a_key_named_for_the_other_part_still_links(tmp_path):
    import csv

    from profiling import run

    folder = tmp_path / "set"
    folder.mkdir()
    with (folder / "person.csv").open("w", newline="") as f:
        csv.writer(f).writerows([["id", "full_name"], *[[i, f"Person number {i} of the set"] for i in range(1, 301)]])
    with (folder / "person_detail.csv").open("w", newline="") as f:
        csv.writer(f).writerows([["person_id", "shoe_size"], *[[i, 30 + i % 15] for i in range(1, 301)]])
    links = {(r["from"]["part"], r["to"]["part"]) for r in run.profile_inputs({"set": str(folder)}, "x")["relationships"]}
    assert ("person_detail", "person") in links
