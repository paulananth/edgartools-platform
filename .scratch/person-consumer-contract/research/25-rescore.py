"""Ticket 25: re-score research 21's census with the repaired normalizer.

The resolution criterion: "each defect fixed with a regression case and the
research 21 census re-scores unchanged or better." This script re-parses every
record the census touched with the production module
`edgar_warehouse.domain.policy.person_name` (v2) and scores the same things
research 21 did, with research 17's normalizer (v1, read from
`r17/records.parquet`) scored alongside as the control:

1. The 938 labelled pairs (`21-pairs.jsonl`): Tier B precision and one-sided
   97.5% Wilson bounds on the eligible key-matched set, and recall on the 934
   `same` pairs. An `ineligible` pair must not be key-matched *and* eligible.
2. Form 3/4/5's same-issuer homonym CIK pairs -- identifier-labelled
   `different` -- and how many the fixed key merges (v1: 1 of 11, Zegna).
3. The defect counts research 21 measured: middle initials lost to `V`,
   particles parsed as the given name, and the two non-person rows.

Sockets blocked. No SEC request.

Run (from the repo root, so the production package imports):
  PYTHONPATH=. uv run --no-project --with pandas --with pyarrow \
    python .scratch/person-consumer-contract/research/25-rescore.py
"""
from __future__ import annotations

import importlib.util
import itertools
import json
from collections import Counter
from pathlib import Path

import pandas as pd

HERE = Path(__file__).resolve().parent
_spec = importlib.util.spec_from_file_location("c21", HERE / "21-common.py")
c21 = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(c21)
c17 = c21.c17

from edgar_warehouse.domain.policy import person_name as v2  # noqa: E402

PARTICLES = v2.SURNAME_PARTICLES


def parse_v2(source: str, raw: str) -> v2.PersonName:
    return v2.parse_conformed(raw) if source == "f4" else v2.parse_western(raw)


def eligible_v2(source: str, raw: str) -> bool:
    if source == "f4":
        return parse_v2(source, raw).shape
    return v2.is_person_name_candidate(raw)


def lcb(k: int, n: int) -> float | None:
    return round(c17.wilson_lower(k, n, c17.Z975), 5) if n else None


# ---------------------------------------------------------------- 1. labelled pairs
P = [json.loads(line) for line in open(HERE / "21-pairs.jsonl")]


def side(p: dict, s: str) -> tuple[str, str]:
    r = p[s]
    return r["rec_id"].split(":", 1)[0], r["raw_name"]


def v2_match(p: dict) -> tuple[bool, bool]:
    (sa, ra), (sb, rb) = side(p, "a"), side(p, "b")
    a, b = parse_v2(sa, ra), parse_v2(sb, rb)
    key = a.key_mi == b.key_mi and a.generational == b.generational and bool(a.last and a.first)
    return key, eligible_v2(sa, ra) and eligible_v2(sb, rb)


def score(rows: list[tuple[bool, bool, str]]) -> dict:
    matched = [lab for key, elig, lab in rows if key and elig]
    c = Counter(matched)
    n = c["same"] + c["unknown"] + c["different"]
    return {
        "key_matched_eligible": len(matched),
        "labels": dict(c),
        "n": n,
        "precision_optimistic": round((c["same"] + c["unknown"]) / n, 5) if n else None,
        "lcb975_optimistic": lcb(c["same"] + c["unknown"], n),
        "precision_conservative": round(c["same"] / n, 5) if n else None,
        "lcb975_conservative": lcb(c["same"], n),
        "ineligible_that_reach_the_key": c["ineligible"],
    }


# v1 control: research 21's own flags. An `ineligible` label was a v1 eligibility
# miss by definition, so v1 counts both as eligible (that is the defect).
v1_rows = [(p["key_fixed"], True, p["label"]) for p in P]
v2_rows = [(*v2_match(p), p["label"]) for p in P]
same_fl = [p for p in P if p["match"]["fl"] and p["label"] == "same"]
v2_by_id = {p["pair_id"]: m for p, m in zip(P, v2_rows)}
out: dict = {
    "labelled_pairs": len(P),
    "v1": score(v1_rows),
    "v2": score(v2_rows),
    "recall": {
        "labelled_same_raised_by_tier_c": len(same_fl),
        "v1_fixed_key_matches": sum(1 for p in same_fl if p["key_fixed"]),
        "v2_fixed_key_matches": sum(1 for p in same_fl if v2_by_id[p["pair_id"]][0]),
    },
    "pairs_whose_decision_changed": [
        {"a": p["a"]["raw_name"], "b": p["b"]["raw_name"], "label": p["label"],
         "v1_key": p["key_fixed"], "v2_key": m[0], "v2_eligible": m[1]}
        for p, m in zip(P, v2_rows) if p["key_fixed"] != m[0] or (p["label"] == "ineligible")
    ],
}
for tag in ("v1", "v2"):
    r = out["recall"]
    r[f"{tag}_recall"] = round(r[f"{tag}_fixed_key_matches"] / r["labelled_same_raised_by_tier_c"], 5)

# ---------------------------------------------------------------- 2. identifier-labelled homonyms
rec = pd.read_parquet(c21.R17 / "records.parquet")
f4 = rec[(rec["source"] == "f4") & (rec["event_type"] == "person") & (rec["xref"] != "")].copy()
parsed = f4["raw_name"].map(v2.parse_conformed)
f4["v2_shape"] = parsed.map(lambda x: x.shape)
f4["v2_kmi"] = parsed.map(lambda x: x.key_mi)
f4["v2_kfl"] = parsed.map(lambda x: f"{x.last}|{x.first}")
f4["v2_gen"] = parsed.map(lambda x: "|".join(sorted(x.generational)))


def homonyms(df: pd.DataFrame, shape_col: str, kfl: str, merge) -> list[dict]:
    df = df[df[shape_col]]
    rep = df.sort_values(["filing", "rec_id"]).drop_duplicates(["ctx", "xref", "raw_name"])
    found = []
    for (_ctx, _k), g in rep.groupby(["ctx", kfl]):
        ids = sorted(g["xref"].unique())
        for x, y in itertools.combinations(ids, 2):
            ga, gb = g[g["xref"] == x], g[g["xref"] == y]
            found.append({"issuer": ga["firm_name"].iloc[0], "a": sorted(set(ga["raw_name"])),
                          "b": sorted(set(gb["raw_name"])),
                          "merged": any(merge(ra, rb) for ra in ga.itertuples() for rb in gb.itertuples())})
    return found


h1 = homonyms(f4, "shape", "k_fl",
              lambda a, b: c21.fixed_key_match(a.k_mi, b.k_mi, a.suffix, b.suffix))
h2 = homonyms(f4, "v2_shape", "v2_kfl",
              lambda a, b: a.v2_kmi == b.v2_kmi and a.v2_gen == b.v2_gen)
# Research 21's own 11 pairs, re-judged by v2 key: merge iff any v2 key coincides.
v2_on_v1_pairs = []
for h in h1:
    ga = [v2.parse_conformed(n) for n in h["a"]]
    gb = [v2.parse_conformed(n) for n in h["b"]]
    v2_on_v1_pairs.append(any(x.key_mi == y.key_mi and x.generational == y.generational for x in ga for y in gb))
out["form345_homonym_cik_pairs"] = {
    "v1_pairs": len(h1),
    "v1_fixed_key_merges": sum(h["merged"] for h in h1),
    "v1_merged": [h for h in h1 if h["merged"]],
    "same_11_pairs_v2_fixed_key_merges": sum(v2_on_v1_pairs),
    "v2_pairs_reenumerated_by_v2_surname_and_given": len(h2),
    "v2_fixed_key_merges": sum(h["merged"] for h in h2),
    "v2_merged": [h for h in h2 if h["merged"]],
}

# ---------------------------------------------------------------- 3. the defects, counted
k8 = rec[rec["source"] == "8k"]
f4all = rec[(rec["source"] == "f4") & (rec["event_type"] == "person")]


def counts(df: pd.DataFrame, source: str) -> dict:
    names = df["raw_name"].fillna("")
    v2p = names.map(lambda n: parse_v2(source, n))
    v1_v_lost = int(((df["suffix"].fillna("").str.split(" ").map(lambda s: "V" in s))
                     & (df["middle"].fillna("") == "")).sum())
    return {
        "records": int(len(df)),
        "v1_middle_initial_lost_to_V": v1_v_lost,
        "v2_middle_initial_lost_to_V": int(sum(1 for p in v2p if "V" in p.suffixes)),
        "v1_given_name_is_a_particle": int(df["first"].isin(PARTICLES).sum()),
        "v2_given_name_is_a_particle": int(sum(1 for p in v2p if p.first in PARTICLES)),
    }


# Research 21 counted on v1-shaped records (`rec[rec["shape"]]`); same population here.
out["defect_counts"] = {"8k": counts(k8[k8["shape"]], "8k"),
                        "form345": counts(f4all[f4all["shape"]], "f4")}

# Review B1: records whose shape (and so eligibility for the key) moves between v1 and v2.
f4_v2_shape = f4all["raw_name"].fillna("").map(lambda n: v2.parse_conformed(n).shape)
out["defect_counts"]["form345_shape_change"] = {
    "v1_shape_v2_not": int((f4all["shape"] & ~f4_v2_shape).sum()),
    "v2_shape_v1_not": int((~f4all["shape"] & f4_v2_shape).sum()),
    "v1_shape_v2_not_names": sorted(set(f4all.loc[f4all["shape"] & ~f4_v2_shape, "raw_name"]))[:40],
    "v2_shape_v1_not_names": sorted(set(f4all.loc[~f4all["shape"] & f4_v2_shape, "raw_name"]))[:40],
}
elig_v1 = k8["shape"]
elig_v2 = k8["raw_name"].fillna("").map(v2.is_person_name_candidate)
out["defect_counts"]["8k_eligibility"] = {
    "v1_eligible": int(elig_v1.sum()),
    "v2_eligible": int(elig_v2.sum()),
    "eligible_v1_not_v2": sorted(set(k8.loc[elig_v1 & ~elig_v2, "raw_name"]))[:40],
    "eligible_v2_not_v1": sorted(set(k8.loc[~elig_v1 & elig_v2, "raw_name"]))[:40],
    "effective_date_eligible_v2": bool(v2.is_person_name_candidate("Effective Date")),
    "manufacturers_bank_eligible_v2": bool(v2.is_person_name_candidate("Manufacturers Bank")),
}
out["normalizer"] = v2.NORMALIZER_VERSION
out["records_parquet_sha256"] = c17.sha256_file(c21.R17 / "records.parquet")

(HERE / "25-rescore.json").write_text(json.dumps(out, indent=1, default=str))
print(json.dumps({k: v for k, v in out.items() if k not in ("pairs_whose_decision_changed",)},
                 indent=1, default=str)[:6000])
