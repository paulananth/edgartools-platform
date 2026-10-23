"""Ticket 133: the RDM draft of `corporate-tax-rates` from the one captured OECD table.

    python3 -I .scratch/company-financials/tax-rates/draft_rates.py \
        <capture folder> rules/reference/published/sec-place-codes/1/canonical.jsonl <draft out file>

The capture folder holds `cit.csv` (OECD Corporate Tax Statistics, dataflow
OECD.CTP.TPS,DSD_TAX_CIT@DF_CIT 2.0) and `receipt.json`. The rate is the
combined central and sub-central statutory rate (MEASURE CIT_C, TARGETING ST,
SECTOR S13), as published, in percent of taxable income. Each country is a code
keyed by its ISO 3166 alpha-2 code with an exact crosswalk to OECD's alpha-3
code; each year is a child code dated 1 January to 31 December holding that
year's rate. Nothing is converted or rounded.
"""
from __future__ import annotations

import csv
import json
import re
import sys
from collections import Counter
from pathlib import Path

CAPTURE, PLACES, OUT = (Path(a) for a in sys.argv[1:4])
UNIT = "percent of taxable income"

# ISO 3166-1 alpha-2 for the jurisdictions whose OECD name differs from the SEC
# place code's label (Canada is filed there by province). Public standard codes.
BY_STANDARD = {"CAN": "CA", "CHN": "CN", "CIV": "CI", "COD": "CD", "CPV": "CV", "CUW": "CW", "CZE": "CZ",
               "GGY": "GG", "HKG": "HK", "KAZ": "KZ", "KOR": "KR", "MAC": "MO", "MDA": "MD", "MKD": "MK",
               "SVK": "SK", "SWZ": "SZ", "TUR": "TR", "VGB": "VG"}


def main() -> None:
    receipt = json.loads((CAPTURE / "receipt.json").read_text())
    rows = [r for r in csv.DictReader((CAPTURE / "cit.csv").open(encoding="utf-8"))
            if (r["MEASURE"], r["TARGETING"], r["SECTOR"]) == ("CIT_C", "ST", "S13")]
    assert {r["UNIT_MEASURE"] for r in rows} == {"PT_INC_TAX"} and {r["UNIT_MULT"] for r in rows} == {"0"}
    assert {r["FREQ"] for r in rows} == {"A"}
    keys = Counter((r["REF_AREA"], r["TIME_PERIOD"]) for r in rows)
    assert max(keys.values()) == 1, "one rate per country and year"

    # Alpha-3 to alpha-2: the SEC place codes' ISO crosswalk by country name,
    # a country (two letters) over a US state of the same name, then the standard.
    by_name: dict[str, set] = {}
    for line in PLACES.read_text(encoding="utf-8").splitlines():
        place = json.loads(line)
        for to_set, _, code, match in place["crosswalk"]:
            if to_set == "iso-3166" and match == "exact" and "-" not in code:
                by_name.setdefault(place["label"].upper(), set()).add(code)
    names = {r["REF_AREA"]: r["Reference area"] for r in rows}
    alpha2 = {}
    for alpha3, name in names.items():
        found = by_name.get(name.upper(), set())
        alpha2[alpha3] = BY_STANDARD.get(alpha3) or (found.pop() if len(found) == 1 else None)
    missing = sorted(a for a, b in alpha2.items() if b is None)
    assert not missing, f"no ISO alpha-2 for {missing}"
    assert len(set(alpha2.values())) == len(alpha2), "two jurisdictions share an alpha-2 code"

    codes, crosswalk = [], []
    for alpha3, name in sorted(names.items(), key=lambda kv: alpha2[kv[0]]):
        code = alpha2[alpha3]
        codes.append({"code": code, "label": name})
        crosswalk.append({"from_code": code, "to_set": "iso-3166-alpha-3", "to_version": "outside",
                          "to_code": alpha3, "match_type": "exact"})
    for r in sorted(rows, key=lambda r: (alpha2[r["REF_AREA"]], r["TIME_PERIOD"])):
        value = r["OBS_VALUE"]
        assert re.fullmatch(r"-?[0-9]+(\.[0-9]+)?", value), value  # plain decimal text, as the store requires
        year = r["TIME_PERIOD"]
        codes.append({"code": f"{alpha2[r['REF_AREA']]}:{year}", "label": f"{r['Reference area']} {year}",
                      "parent_code": alpha2[r["REF_AREA"]], "valid_from": f"{year}-01-01", "valid_to": f"{year}-12-31",
                      "value": value, "unit": UNIT})
    draft = {
        "code_set": {"code_set": "corporate-tax-rates", "name": "Statutory corporate income tax rates",
                     "definition": "Each jurisdiction's combined central and sub-central statutory corporate income "
                                   "tax rate for each year, as the OECD publishes it, in percent of taxable income.",
                     "authority": "OECD Corporate Tax Statistics", "steward": "operator"},
        "version": "1",
        "created_by": "Claude (company-financials, ticket 133)",
        "evidence": {"source": receipt["url"], "fetched_at": receipt["fetched_at"], "sha256": receipt["sha256"],
                     "bytes": receipt["bytes"], "series": "MEASURE CIT_C, TARGETING ST, SECTOR S13",
                     "countries": len(names), "rates": len(rows),
                     "years": [min(r["TIME_PERIOD"] for r in rows), max(r["TIME_PERIOD"] for r in rows)],
                     "alpha2_from_place_codes": len(names) - len(BY_STANDARD), "alpha2_from_standard": len(BY_STANDARD)},
        "codes": codes,
        "levels": [{"depth": 1, "name": "jurisdiction"}, {"depth": 2, "name": "year"}],
        "crosswalk": crosswalk,
        "usage": [{"store": "other", "object": "company measures", "field": "ROIC tax rate",
                   "note": "The filer's country of incorporation; the year whose period holds the fiscal year end"}],
        "hints": [{"kind": "meaning", "text": "A statutory corporate income tax rate: central plus sub-central, before incentives"},
                  {"kind": "use_when", "text": "ROIC needs a tax rate and the filer's effective rate is not meaningful "
                                              "(pretax income zero or negative, or the rate outside 0 to 100 percent)"},
                  {"kind": "avoid_when", "text": "A filer's own effective rate is meaningful; use that instead"}],
    }
    OUT.write_text(json.dumps(draft, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(json.dumps({"countries": len(names), "rates": len(rows), "codes": len(codes), "years": draft["evidence"]["years"],
                      "alpha2_from_standard": len(BY_STANDARD)}))


if __name__ == "__main__":
    main()
