"""SEC's state and country codes are one reference table in `rules/`.

`rules/reference/sec-place-codes.yaml` holds SEC's whole list of EDGAR codes,
as edgartools ships it, with an ISO code for each. `names.edgar_jurisdiction`
reads it (rules skill ticket 08).
"""

from __future__ import annotations

import csv
import re
from pathlib import Path

import pytest

import edgar
from edgar_warehouse.mdm.clean.names import edgar_jurisdiction, jurisdictions_agree
from edgar_warehouse.mdm.clean.store import digest
from edgar_warehouse.rules import files

TABLE = files.reference("sec-place-codes")["codes"]

# The 169 codes the table held before it moved (company mastering ticket 08),
# and the digest of what each one read as. Moving the table changed none of
# them.
BEFORE = [
    "1E", "1H", "1P", "1Q", "1T", "1U", "1Z", "2A", "2B", "2J", "2K", "2M", "2N", "A0",
    "A1", "A2", "A3", "A4", "A5", "A6", "A8", "A9", "AK", "AL", "AR", "AZ", "B1", "B9",
    "C0", "C1", "C3", "C4", "C5", "C6", "C8", "C9", "CA", "CO", "CT", "D0", "D1", "D5",
    "D6", "D8", "DC", "DE", "E0", "E9", "F3", "F4", "F5", "F8", "FL", "G2", "G4", "G7",
    "G8", "GA", "GU", "H1", "H2", "H3", "H9", "HI", "I0", "IA", "ID", "IL", "IN", "J1",
    "J3", "K3", "K5", "K6", "K7", "K8", "KS", "KY", "L2", "L3", "L6", "L7", "L8", "LA",
    "M0", "M2", "M3", "M5", "M6", "M8", "MA", "MD", "ME", "MI", "MN", "MO", "MS", "MT",
    "N0", "N2", "N4", "N8", "NC", "ND", "NE", "NH", "NJ", "NM", "NV", "NY", "O1", "O4",
    "O5", "O9", "OH", "OK", "OR", "P4", "P7", "P8", "PA", "PR", "Q1", "Q2", "Q5", "Q8",
    "R0", "R1", "R5", "R6", "R9", "RI", "S1", "S3", "SC", "SD", "T0", "T3", "TN", "TX",
    "U0", "U3", "U7", "UT", "V6", "V7", "V8", "VA", "VI", "VT", "W0", "W1", "W5", "W6",
    "W8", "WA", "WI", "WV", "WY", "X0", "X1", "X3", "X5", "Y0", "Y7", "Y8", "Y9", "Z2",
    "Z4",
]  # fmt: skip
BEFORE_DIGEST = "51f54ac5f32f11d6231d6c29dc781f8dc6cabea24deedffba3b93ff0d91aa9c1"


def test_the_table_is_secs_whole_list_as_edgartools_ships_it():
    shipped = Path(edgar.__file__).parent / "reference" / "data" / "place_codes.csv"
    with shipped.open(newline="") as handle:
        sec = {row["Code"]: (row["Place"], row["Type"]) for row in csv.DictReader(handle)}
    assert {code: (row["place"], row["type"]) for code, row in TABLE.items()} == sec


def test_every_code_but_unknown_has_an_iso_code():
    assert [code for code, row in TABLE.items() if row["iso"] is None] == ["XX"]
    for code, row in TABLE.items():
        if row["iso"] is not None:
            assert re.fullmatch(r"[A-Z]{2}(-[A-Z0-9]{1,3})?", row["iso"]), code


def test_the_codes_placed_before_the_move_read_the_same():
    assert len(BEFORE) == 169
    assert digest({code: edgar_jurisdiction(code) for code in BEFORE}) == BEFORE_DIGEST


@pytest.mark.parametrize(
    ("code", "iso"),
    [("N5", "MO"), ("E3", "KH"), ("1B", "AM"), ("Z5", "ME"), ("A7", "CA-PE"), ("1V", "US-MP")],
)
def test_a_code_seen_in_bronze_or_added_now_is_placed(code, iso):
    assert edgar_jurisdiction(code) == iso


def test_a_us_territory_agrees_with_its_own_country_code():
    assert jurisdictions_agree("US-MP", "MP")
    assert jurisdictions_agree("US-AS", "AS")
