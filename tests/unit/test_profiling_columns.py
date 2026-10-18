"""Column profile, identifier detectors and sensitivity tags of the data-profiling skill."""

import random
import string
import sys
from pathlib import Path

import pytest

duckdb = pytest.importorskip("duckdb")  # in the mdm extra, which CI installs

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "skills" / "data-profiling" / "scripts"))
from profiling import identifiers, profile, sensitivity  # noqa: E402
from profiling.identifiers import BASE36  # noqa: E402

rng = random.Random(3)


def with_mod97(base: str) -> str:
    n = int("".join(str(BASE36[c]) for c in base + "00"))
    return f"{base}{98 - n % 97:02d}"


def with_luhn(base: str) -> str:
    for d in "0123456789":
        if identifiers.luhn(base + d):
            return base + d
    raise AssertionError


def with_family(test, base: str, alphabet: str) -> str:
    return next(base + c for c in alphabet if test(base + c))


def digits(n: int) -> str:
    return "".join(rng.choice(string.digits) for _ in range(n))


def alnum(n: int) -> str:
    return "".join(rng.choice(string.digits + string.ascii_uppercase) for _ in range(n))


@pytest.mark.parametrize("family, make", [
    ("mod 97-10", lambda: with_mod97(alnum(18))),
    ("luhn", lambda: with_luhn(digits(15))),
    ("mod 11-2", lambda: with_family(identifiers.mod11_2, digits(9), "0123456789X")),
    ("mod 11-10", lambda: with_family(identifiers.mod11_10, digits(9), string.digits)),
    ("mod 37-36", lambda: with_family(identifiers.mod37_36, alnum(9), string.digits + string.ascii_uppercase)),
    ("damm", lambda: with_family(identifiers.damm, digits(9), string.digits)),
    # FIGI-shaped: eleven letters or digits and a check digit doubled from the left (ticket 107).
    ("luhn over letter values from the left",
     lambda: with_family(identifiers.luhn_letter_values_from_left, alnum(11), string.digits)),
])
def test_each_family_is_found_on_valid_values(family, make):
    found = identifiers.check_digits([make() for _ in range(500)])
    assert found["family"] == family and found["pass_rate"] == 1.0


def test_an_odd_length_column_keeps_luhn_over_letter_values():
    # On a value of odd length, doubling from the left doubles what Luhn from the right does: the
    # two families tie, and the one listed first names the column (a CUSIP-shaped column).
    values = [with_family(identifiers.luhn_letter_values, alnum(8), string.digits) for _ in range(500)]
    found = identifiers.check_digits(values)
    assert found["rates"]["luhn over letter values from the left"] == 1.0
    assert found["family"] == "luhn over letter values"


def test_random_values_pass_only_at_chance_and_name_no_family():
    found = identifiers.check_digits([digits(10) for _ in range(5000)])
    assert found["family"] is None
    assert 0.05 < found["rates"]["luhn"] < 0.15  # about 1 in 10, by chance alone


def test_a_family_with_defects_is_still_the_family():
    # 70% pass: seven times chance, so the column holds that check digit and 30% of its values are
    # defects (a security id column where options carry invented issue numbers).
    values = [with_luhn(digits(9)) for _ in range(700)] + [d for d in (digits(10) for _ in range(600))
                                                           if not identifiers.luhn(d)][:300]
    found = identifiers.check_digits(values)
    assert found["family"] == "luhn" and found["defective"] and 0.6 < found["pass_rate"] < 0.8


def test_a_clean_family_is_not_defective():
    assert identifiers.check_digits([with_luhn(digits(9)) for _ in range(500)])["defective"] is False


def test_a_ten_percent_luhn_pass_is_noise():
    values = [with_luhn(digits(9)) for _ in range(10)] + [digits(10) for _ in range(90)]
    assert identifiers.check_digits(values)["family"] is None


@pytest.fixture
def con():
    c = duckdb.connect()
    c.execute("""CREATE TABLE t AS SELECT i AS k, 'ID' || lpad(CAST(i AS VARCHAR), 6, '0') AS code,
                 CASE WHEN i % 4 = 0 THEN NULL ELSE 'Some Long Name ' || i END AS label,
                 i % 3 AS small FROM range(1, 1001) r(i)""")
    return c


def test_profile_counts_are_exact(con):
    cols = {c["name"]: c for c in profile.columns(con, "t")}
    assert cols["k"]["unique"] == 1.0 and cols["k"]["distinct"] == 1000
    assert cols["label"]["fill"] == 0.75 and cols["label"]["non_null"] == 750
    assert cols["code"]["shape"] == "AA999999" and cols["code"]["shape_share"] == 1.0
    assert cols["small"]["distinct"] == 3
    assert cols["label"]["tokens"] == 4.0
    assert cols["k"]["min"] == "1" and cols["k"]["max"] == "1000"


def test_identifier_shape_and_dense_sequence(con):
    cols = {c["name"]: c for c in profile.columns(con, "t")}
    assert identifiers.identifier_shaped(cols["code"])
    assert not identifiers.identifier_shaped(cols["label"])
    assert not identifiers.identifier_shaped(cols["small"])
    assert identifiers.dense_sequence(cols["k"])


def test_words_split_names():
    assert sensitivity.words("GivenName") == ["given", "name"]
    assert sensitivity.words("date_of_birth") == ["date", "of", "birth"]
    assert sensitivity.words("HTTPStatusCode") == ["http", "status", "code"]


def test_personal_words_count_only_in_parts_about_people():
    people = sensitivity.person_part(["Key", "GivenName", "Surname", "City"])
    assert people
    assert not sensitivity.person_part(["Key", "Name", "StreetAddress"])
    assert sensitivity.tag("StreetAddress", ["1 A St"], people)["sensitivity"] == "personal"
    assert sensitivity.tag("StreetAddress", ["1 A St"], False)["sensitivity"] == "none"
    assert sensitivity.tag("City", ["X"], people)["sensitivity"] == "none"


def test_a_name_column_holding_peoples_names_makes_its_part_about_people():
    people = ["Ann B. Cole", "COLE ANN", "Smith, John A", "O'Brien Mary-Kate", "/s/ Lee Park, Attorney-in-Fact",
              "Acme Trust"]
    firms = ["Acme Widgets, Inc.", "North River Capital LLC", "Blue Fund", "Zeta Holdings", "Lee Park, Inc.",
             "Unit 9 Labs", "Nordwind", "Stavby Sever s.r.o.", "Mlyn Sever, a.s."]
    assert [sensitivity.person_name(v) for v in people] == [True, True, True, True, True, False]
    assert not any(sensitivity.person_name(v) for v in firms)
    assert sensitivity.names_people("rptOwnerName", people)
    assert not sensitivity.names_people("issuer_name", firms)
    assert sensitivity.names_people("signer", people) and sensitivity.names_people("holder", people)
    assert not sensitivity.names_people("remarks", people)  # the vote counts only on a column named for people
    assert sensitivity.tag("signatureName", people, False) == {"sensitivity": "personal",
                                                               "signals": ["values: people's names"]}
    assert sensitivity.tag("LegalName", firms, False)["sensitivity"] == "none"
    assert not sensitivity.names_people("Entity.OtherEntityName", people)  # a column named for organisations


def test_place_and_thing_names_are_not_read_as_peoples_names():
    # Two capitalised words, like a person's name; the column's name says what they are.
    for column, values in (("city_name", ["New York", "Los Angeles", "San Diego", "Las Vegas"]),
                           ("CountryName", ["United States", "South Africa", "New Zealand"]),
                           ("instrument_name", ["Common Stock", "Corporate Bond", "Treasury Note"]),
                           ("CategoryName", ["Cell phones", "Home Appliances"]),
                           ("owner_street", ["Elm Road", "Oak Lane"])):
        assert sensitivity.tag(column, values, False)["sensitivity"] == "none", column


def test_sensitive_personal_from_words_and_values():
    assert sensitivity.tag("TaxId", ["1"], False)["sensitivity"] == "sensitive_personal"
    assert sensitivity.tag("Tax", ["1"], False)["sensitivity"] == "none"
    assert sensitivity.tag("Religion", ["x"], False)["sensitivity"] == "sensitive_personal"
    cards = [with_luhn(digits(15)) for _ in range(20)]
    assert sensitivity.tag("ref", cards, False)["sensitivity"] == "sensitive_personal"


def test_mask_keeps_shape_only():
    assert sensitivity.mask("Ann B. Cole-9") == "Aaa A. Aaaa-9"
    assert sensitivity.mask("123-45-6789") == "999-99-9999"
    assert sensitivity.mask(None) is None


def test_published_check_digit_vectors():
    # Examples from python-stdnum's ISO 7064 modules; 120,000 random values also
    # agreed with python-stdnum when these validators were written.
    assert identifiers.mod11_10("794623") and not identifiers.mod11_10("794624")
    assert identifiers.mod37_36("A12425GABC1234002M") and not identifiers.mod37_36("A12425GABC1234002N")
    assert identifiers.luhn("79927398713") and not identifiers.luhn("79927398710")


def test_logical_type_of_dates_stored_as_text():
    con = duckdb.connect()
    con.execute("CREATE TABLE d AS SELECT '2025-01-0' || i AS day, 'x' || i AS other FROM range(1, 9) r(i)")
    cols = {c["name"]: c for c in profile.columns(con, "d")}
    assert profile.logical_type(cols["day"]) == "DATE" and cols["day"]["type"] == "VARCHAR"
    assert profile.logical_type(cols["other"]) == "VARCHAR"


def test_first_and_last_mean_a_person_only_next_to_name():
    assert not sensitivity.person_part(["FirstAddressLine", "LastUpdateDate", "LegalName"])
    assert sensitivity.person_part(["first_name", "last_name"])
    assert sensitivity.person_part(["GivenName", "Surname"])


def test_dates_written_in_two_formats_are_still_dates():
    con = duckdb.connect()
    con.execute("""CREATE TABLE d AS SELECT CASE WHEN i % 2 = 0 THEN '2022-03-14T17:34:27Z'
                   ELSE '2022-03-14T17:34:27.107Z' END AS at_time FROM range(10) r(i)""")
    col = profile.columns(con, "d")[0]
    assert col["shape_share"] == 0.5 and col["temporal_share"] == 1.0 and profile.is_temporal(col)


def test_numbers_issued_under_a_prefix_are_identifier_shaped_but_amounts_are_not():
    con = duckdb.connect()
    rng = random.Random(7)
    n = 300
    columns = {
        "reg": [f"8-{rng.randint(10, 999999)}" for _ in range(n)],  # 4 to 8 characters, one prefix
        "amount": [str(rng.randint(1, 10**rng.randint(1, 9))) for _ in range(n)],
        "price": [f"{rng.randint(1, 99999)}.{rng.randint(0, 99)}" for _ in range(n)],
        "day": [f"{rng.randint(1, 12)}/{rng.randint(1, 28)}/20{rng.randint(10, 26)}" for _ in range(n)],
        "one_month": [f"3/{rng.randint(1, 28)}/20{rng.randint(10, 26)}" for _ in range(n)],  # one prefix, still dates
        "iso_day": [f"20{rng.randint(10, 26)}-{rng.randint(1, 12)}-{rng.randint(1, 28)}" for _ in range(n)],
        "time": [f"{rng.randint(0, 23)}:{rng.randint(0, 59):02d}" for _ in range(n)],
        "range": [f"{rng.randint(1, 999)}-{rng.randint(1000, 99999)}" for _ in range(n)],
        "fraction": [f"{rng.randint(1, 9)}/{rng.randint(10, 999)}" for _ in range(n)],
        "words": [f"{rng.choice(['smith', 'lee', 'ng', 'garcia'])}-{''.join(rng.choices('abcdefgh', k=rng.randint(2, 9)))}"
                  for _ in range(n)],
    }
    con.execute("CREATE TABLE r (" + ", ".join(f"{name} VARCHAR" for name in columns) + ")")
    con.executemany(f"INSERT INTO r VALUES ({', '.join('?' * len(columns))})", list(zip(*columns.values())))
    cols = {c["name"]: c for c in profile.columns(con, "r")}
    assert cols["reg"]["pattern"] == "9-9" and cols["reg"]["length_share"] < 0.99
    assert identifiers.shape_test(cols["reg"])["test"] == "one pattern under one prefix"
    assert identifiers.identifier_shaped(cols["reg"])
    for name in columns:
        if name != "reg":
            assert not identifiers.identifier_shaped(cols[name]), name


def test_the_letter_value_family_reads_as_the_identifier_type_does():
    # `*@#` read as 36-38 (a private placement's issue number), as the engine's declared type reads them.
    from edgar_warehouse.mdm.clean import identifier_types
    rng = random.Random(7)
    chars = string.digits + string.ascii_uppercase + "*@#"
    for _ in range(500):
        value = "".join(rng.choice(chars) for _ in range(9))
        assert identifiers.luhn_letter_values(value) == identifier_types.luhn_letter_values(value)
