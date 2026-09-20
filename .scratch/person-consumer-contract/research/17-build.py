"""Research 17, stage 1: build one record table across the four Person sources and run the
census (eligible population, key groups, id disagreement, recall of the id-labelled pairs,
Tier C review volume). Writes scratchpad r17/records.parquet and research/17-census.json.

Run: uv run --no-project --with duckdb --with pandas --with pyarrow --with pytz python 17-build.py
"""
from __future__ import annotations

import importlib.util
import itertools
import json
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import duckdb
import pandas as pd

spec = importlib.util.spec_from_file_location("c17", Path(__file__).with_name("17-common.py"))
c17 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(c17)

con = duckdb.connect()
rows: list[dict] = []
CENSUS_ONLY = "--census-only" in sys.argv and (c17.R17 / "records.parquet").exists()


def add(source, rec_id, ctx, raw_name, parsed, xref, month, filing, roles, extra):
    keys = c17.name_keys(parsed)
    rows.append({
        "source": source, "rec_id": rec_id, "ctx": str(ctx), "raw_name": raw_name,
        "last": parsed["last"], "first": parsed["first"], "middle": " ".join(parsed["middle"]),
        "suffix": " ".join(parsed["suffix"]), "shape": bool(parsed["shape"]),
        "k_full": keys["full"], "k_nosuffix": keys["nosuffix"], "k_mi": keys["mi"], "k_fl": keys["fl"],
        "block": c17.block_key(parsed), "xref": (str(xref).strip() if isinstance(xref, (str, int)) and str(xref).strip() not in ("", "nan", "None") else ""),
        "month": month, "filing": str(filing), "roles": "|".join(sorted(roles)), **extra,
    })


# ---- ADV Schedule A/B, I rows, March + August ---------------------------------------------------
for month, ab, base in ([] if CENSUS_ONLY else [("2026-03", c17.ADV_MAR_AB, c17.ADV_MAR_BASE),
                        ("2026-08", c17.ADV_AUG_AB, c17.ADV_AUG_BASE)]):
    df = con.sql(f"""
        select a."FilingID" filing, trim(b."1E1") firm_crd, b."1A" firm_name, a."Schedule" schedule,
               a."Full Legal Name" fullname, a."Title or Status" title, a."Status Acquired" acquired,
               a."Ownership Code" own_code, a."Control Person" control, trim(a."OwnerID") owner_id,
               b."DateSubmitted" submitted, a."Entity in Which" entity_in_which
        from read_csv('{ab}', all_varchar=true) a
        join read_csv('{base}', all_varchar=true) b on a."FilingID" = b."FilingID"
        where a."DE/FE/I" = 'I'
    """).df()
    for i, r in enumerate(df.itertuples(index=False)):
        p = c17.parse_adv(r.fullname)
        add("adv", f"adv:{month}:{r.filing}:{i}", r.firm_crd, r.fullname, p, r.owner_id, month, r.filing,
            {c17.role_class_text(r.title)},
            {"title": r.title or "", "acquired": r.acquired or "", "own_code": r.own_code or "",
             "control": r.control or "", "schedule": r.schedule or "", "sub": r.entity_in_which or "",
             "event_type": "", "date": str(r.submitted or ""), "firm_name": r.firm_name or ""})

# ---- Form 3/4/5 reporting owners (research 07 union corpus; officer_title joined from r18) ------
titles = {}
for path in ([] if CENSUS_ONLY else [c17.F4_PRIMARY_ROWS, c17.F4_LEGACY_ROWS]):
    with open(path) as f:
        for line in f:
            d = json.loads(line)
            titles[(d["accession"], d["owner_index"])] = d.get("officer_title", "") or ""
with open(c17.F4_UNION if not CENSUS_ONLY else "/dev/null") as f:
    for line in f:
        d = json.loads(line)
        p = c17.parse_edgar(d["owner_name"])
        roles = c17.role_set_flags(d["flag_combo"])
        add("f4", f"f4:{d['accession']}:{d['owner_index']}", d["issuer_cik"], d["owner_name"], p,
            d["owner_cik"], d["period"][:7] if d.get("period") else "", d["accession"], roles,
            {"title": titles.get((d["accession"], d["owner_index"]), ""), "acquired": "", "own_code": "",
             "control": "", "schedule": d["form"], "sub": d.get("sub_name", "") or "",
             "event_type": d["cj"], "date": d.get("period", "") or "", "firm_name": d["issuer_name"],
             "flag_combo": d["flag_combo"]})

# ---- 8-K Item 5.02 ---------------------------------------------------------------------------------
df = con.sql(f"select * from '{c17.EIGHTK}'").df() if not CENSUS_ONLY else pd.DataFrame()
for r in df.itertuples(index=False):
    p = c17.parse_western(r.person_name if isinstance(r.person_name, str) else "")
    p["shape"] = p["shape"] and not c17.looks_like_role_text(r.person_name if isinstance(r.person_name, str) else "")
    add("8k", f"8k:{r.accession_number}:{r.event_index}", r.cik, r.person_name if isinstance(r.person_name, str) else "", p, None,
        str(r.effective_date)[:7] if pd.notna(r.effective_date) else "", r.accession_number,
        {c17.role_class_text(r.exec_role if isinstance(r.exec_role, str) else "", default="UNK")},
        {"title": r.exec_role if isinstance(r.exec_role, str) else "", "acquired": "", "own_code": "", "control": "", "schedule": "",
         "sub": r.previous_role if isinstance(r.previous_role, str) else "", "event_type": r.event_type or "",
         "date": str(r.effective_date) if pd.notna(r.effective_date) else "", "firm_name": ""})

# ---- DEF 14A executive records -----------------------------------------------------------------------
df = con.sql(f"select * from '{c17.PROXY}'").df() if not CENSUS_ONLY else pd.DataFrame()
for r in df.itertuples(index=False):
    p = c17.parse_western(r.exec_name if isinstance(r.exec_name, str) else "")
    p["shape"] = p["shape"] and not c17.looks_like_role_text(r.exec_name if isinstance(r.exec_name, str) else "")
    add("proxy", f"proxy:{r.accession_number}:{r.fact_key}", r.cik, r.exec_name if isinstance(r.exec_name, str) else "", p, None,
        str(r.fiscal_year), r.accession_number, {c17.role_class_text(r.exec_role if isinstance(r.exec_role, str) else "", default="UNK")},
        {"title": r.exec_role if isinstance(r.exec_role, str) else "", "acquired": "", "own_code": "", "control": "", "schedule": "",
         "sub": "", "event_type": "", "date": str(r.fiscal_year), "firm_name": ""})

if CENSUS_ONLY:
    rec = pd.read_parquet(c17.R17 / "records.parquet")
    rec.loc[rec["xref"].isin(["nan", "None"]), "xref"] = ""
    m = rec["source"].isin(["8k", "proxy"])
    rec.loc[m, "shape"] = rec.loc[m, "shape"] & ~rec.loc[m, "raw_name"].map(c17.looks_like_role_text)
    rec.to_parquet(c17.R17 / "records.parquet", index=False)
else:
    rec = pd.DataFrame(rows)
    if "flag_combo" not in rec:
        rec["flag_combo"] = ""
    rec["flag_combo"] = rec["flag_combo"].fillna("")
    c17.R17.mkdir(exist_ok=True)
    rec.to_parquet(c17.R17 / "records.parquet", index=False)

# ================================ census ==============================================================
census = {"run_et": datetime.now(ZoneInfo("America/New_York")).isoformat(timespec="seconds"),
          "inputs": {}, "sources": {}}
for name, path in (("adv_mar_ab", c17.ADV_MAR_AB), ("adv_aug_ab", c17.ADV_AUG_AB),
                   ("adv_mar_base", c17.ADV_MAR_BASE), ("adv_aug_base", c17.ADV_AUG_BASE),
                   ("f4_union", c17.F4_UNION), ("eightk", c17.EIGHTK), ("proxy", c17.PROXY)):
    census["inputs"][name] = {"path": str(path), "sha256": c17.sha256_file(path)}

ROLE_SUFFIX = "_role"


def census_source(src: pd.DataFrame) -> dict:
    out = {"records": int(len(src)), "person_shaped": int(src["shape"].sum()),
           "xref_present": int((src["xref"] != "").sum()),
           "xref_blank": int((src["xref"] == "").sum()),
           "distinct_ctx": int(src["ctx"].nunique()),
           "distinct_xref": int(src.loc[src["xref"] != "", "xref"].nunique()),
           "variants": {}}
    shaped = src[src["shape"]].copy()
    out["shaped_records"] = int(len(shaped))
    # Tier C candidate presence: another record at the same ctx with same block, not itself
    blk = shaped.groupby(["ctx", "block"])["rec_id"].transform("size")
    shaped["has_block_cand"] = blk > 1
    for v in c17.VARIANTS:
        kcol = f"k_{v}"
        g = shaped.groupby(["ctx", kcol])
        gsize = g["rec_id"].transform("size")
        shaped["has_key_cand"] = gsize > 1
        groups = g.size().rename("n").reset_index()
        nx = shaped[shaped["xref"] != ""].drop_duplicates(["ctx", kcol, "xref"]).groupby(["ctx", kcol]).size().rename("n_xref").reset_index()
        nb = shaped[shaped["xref"] == ""].groupby(["ctx", kcol]).size().rename("n_blank").reset_index()
        groups = groups.merge(nx, how="left", on=["ctx", kcol]).merge(nb, how="left", on=["ctx", kcol]).fillna({"n_xref": 0, "n_blank": 0})
        multi = groups[groups["n"] > 1]
        d = {
            "groups": int(len(groups)),
            "groups_multi_record": int(len(multi)),
            "records_in_multi_groups": int(multi["n"].sum()),
            "groups_with_2plus_xref": int((multi["n_xref"] >= 2).sum()),
            "groups_with_2plus_xref_and_blank": int(((multi["n_xref"] >= 1) & (multi["n_blank"] > 0)).sum()),
            "records_with_key_cand": int(shaped["has_key_cand"].sum()),
            "records_with_block_cand": int(shaped["has_block_cand"].sum()),
            "records_block_cand_no_key_cand": int((shaped["has_block_cand"] & ~shaped["has_key_cand"]).sum()),
        }
        d["review_per_1000"] = round(1000 * d["records_block_cand_no_key_cand"] / max(1, len(shaped)), 2)
        # id-labelled recall: same ctx + same xref pairs (distinct raw names only counted once
        # per (ctx, xref) group): fraction of such groups where all members share the key
        labelled = shaped[shaped["xref"] != ""]
        if len(labelled):
            gx = labelled.groupby(["ctx", "xref"]).agg(n=("rec_id", "size"), nk=(kcol, "nunique"),
                                                        nraw=("raw_name", "nunique")).reset_index()
            gx = gx[gx["n"] > 1]
            d["id_groups_multi"] = int(len(gx))
            d["id_groups_key_split"] = int((gx["nk"] > 1).sum())
            d["id_groups_raw_name_varies"] = int((gx["nraw"] > 1).sum())
            d["recall_id_groups"] = round(1 - d["id_groups_key_split"] / max(1, len(gx)), 5)
        out["variants"][v] = d
    # role consistency within the strict key groups

    return out


for s in ("adv", "f4", "8k", "proxy"):
    census["sources"][s] = census_source(rec[rec["source"] == s])
census["sources"]["f4_person"] = census_source(rec[(rec["source"] == "f4") & (rec["event_type"] == "person")])

# ADV extra: firm CIK bridge population via IA_1D3_CIK (how many ADV firms can meet Form 4 issuers)
cik_map = con.sql(f"""select distinct trim("FilingID") filing, trim("CIK") cik from
    (select * from read_csv('{c17.ADV_MAR_1D3}', all_varchar=true, header=true)
     union all select * from read_csv('{c17.ADV_AUG_1D3}', all_varchar=true, header=true))""").df()
adv = rec[rec["source"] == "adv"]
adv_ciks = set(cik_map.merge(adv[["filing"]].drop_duplicates(), on="filing")["cik"].astype(str))
f4_issuers = set(rec.loc[rec["source"] == "f4", "ctx"])
census["adv_firm_cik_bridge"] = {"adv_filings_with_1d3_cik": int(cik_map["filing"].nunique()),
                                 "distinct_1d3_ciks_in_loaded_months": len(adv_ciks),
                                 "of_which_are_f4_issuers_in_corpus": len({c.lstrip("0") for c in adv_ciks} & {c.lstrip("0") for c in f4_issuers})}

census["wilson"] = {"z_one_sided_95": c17.Z95, "z_one_sided_975": c17.Z975,
                    "n_zero_errors_for_0.99_at_95": c17.n_for_lcb(0.99, c17.Z95),
                    "n_zero_errors_for_0.99_at_975": c17.n_for_lcb(0.99, c17.Z975),
                    "n_one_error_for_0.99_at_95": c17.n_for_lcb(0.99, c17.Z95, 1),
                    "n_one_error_for_0.99_at_975": c17.n_for_lcb(0.99, c17.Z975, 1)}
with open(Path(__file__).with_name("17-census.json"), "w") as f:
    json.dump(census, f, indent=1)
print(json.dumps(census, indent=1))
