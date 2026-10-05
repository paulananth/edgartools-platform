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
])
def test_each_family_is_found_on_valid_values(family, make):
    found = identifiers.check_digits([make() for _ in range(500)])
    assert found["family"] == family and found["pass_rate"] == 1.0


def test_random_values_pass_only_at_chance_and_name_no_family():
    found = identifiers.check_digits([digits(10) for _ in range(5000)])
    assert found["family"] is None
    assert 0.05 < found["rates"]["luhn"] < 0.15  # about 1 in 10, by chance alone


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
