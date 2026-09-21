"""Research 21, stage 1: enumerate the **whole** 8-K Item 5.02 candidate population.

Research 17 sampled this population (140 within-source groups of 216; 140 cross-source rows of
721). Ticket 21 needs n >= 381 labelled pairs at the fixed key, so this stage takes the census
instead: every within-source group and every cross-source row. No new source data is read --
the record table is research 17's `r17/records.parquet`, built by `17-build.py` from the S3
export snapshots and the research 07 bronze union. **Zero SEC EDGAR requests.**

Strata (a pair is two records at the same issuer CIK):

  K  within-source   : same issuer, same `fl` key, two 8-K events on different dates.
                       Census of all such groups; one pair per group (earliest x latest event),
                       which is research 17's own construction.
  X  cross-source    : an 8-K row against a Form 3/4/5 person owner at the same issuer sharing
                       the `fl` key. Census of all such rows; one pair per distinct owner CIK.

Pair ids are built with research 17's hash of the two record ids, so the 281 pairs research 17
already labelled keep their ids and the two studies pool without double counting.

Run: uv run --no-project --with duckdb --with pandas --with pyarrow python 21-sample.py
"""
from __future__ import annotations

import hashlib
import importlib.util
import itertools
import json
from collections import Counter
from pathlib import Path

import pandas as pd

_spec = importlib.util.spec_from_file_location("c21", Path(__file__).with_name("21-common.py"))
c21 = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(c21)
c17 = c21.c17

rec = pd.read_parquet(c21.R17 / "records.parquet")
rec = rec[rec["shape"]].copy()
rec["roles_set"] = rec["roles"].map(lambda s: set(x for x in s.split("|") if x))
k8 = rec[rec["source"] == "8k"]
f4p = rec[(rec["source"] == "f4") & (rec["event_type"] == "person")]
pairs: list[dict] = []


def h(*parts) -> str:
    return hashlib.sha256("|".join(map(str, parts)).encode()).hexdigest()[:12]


def side(r) -> dict:
    return {"rec_id": r.rec_id, "raw_name": r.raw_name, "xref": r.xref, "filing": r.filing,
            "month": r.month, "title": r.title, "roles": r.roles, "acquired": r.acquired,
            "own_code": r.own_code, "control": r.control, "schedule": r.schedule, "sub": r.sub,
            "event_type": r.event_type, "date": r.date, "flag_combo": r.flag_combo,
            "suffix": r.suffix,
            "k_full": r.k_full, "k_nosuffix": r.k_nosuffix, "k_mi": r.k_mi, "k_fl": r.k_fl}


def emit(stratum, a, b, extra=None):
    vm = {v: bool(getattr(a, f"k_{v}") == getattr(b, f"k_{v}")) for v in c17.VARIANTS}
    d = {"pair_id": f"{stratum}-8k-{h(a.rec_id, b.rec_id)}", "stratum": stratum, "source": "8k",
         "ctx": a.ctx, "firm_name": a.firm_name or b.firm_name,
         "key_fields": {"ctx": a.ctx, "a_name": a.raw_name, "b_name": b.raw_name,
                        "a_roles": a.roles, "b_roles": b.roles,
                        "a_suffix": a.suffix, "b_suffix": b.suffix},
         "match": vm,
         "key_fixed": c21.fixed_key_match(a.k_mi, b.k_mi, a.suffix, b.suffix),
         "suffix_veto": c21.suffix_veto(a.suffix, b.suffix),
         "roles_consistent": c17.roles_consistent(a.roles_set, b.roles_set),
         "a": side(a), "b": side(b), "label": "", "evidence": "", "labeler_rule": ""}
    if extra:
        d.update(extra)
    pairs.append(d)
    return d


# ---------- K: 8-K within-source, census of all groups ------------------------------------------
repk = k8.sort_values(["date", "rec_id"]).drop_duplicates(["ctx", "k_full", "filing"])
grpk = [(k, g) for k, g in repk.groupby(["ctx", "k_fl"]) if len(g) >= 2 and g["date"].nunique() >= 2]
grpk.sort(key=lambda kg: h(*kg[0]))          # research 17's order: its first 140 are these first 140
print("K groups (census):", len(grpk), "| research 17 labelled the first 140")

f4_by_issuer = {ctx: g for ctx, g in f4p.groupby("ctx")}


def f4_anchor(ctx, kfl):
    g = f4_by_issuer.get(ctx)
    if g is None:
        return {"f4_issuer_present": False}
    m = g[g["k_fl"] == kfl]
    return {"f4_issuer_present": True, "f4_ciks_with_fl": sorted(set(m["xref"])),
            "f4_names": sorted(set(m["raw_name"])), "f4_flags": sorted(set(m["flag_combo"])),
            "f4_titles": sorted(set(t for t in m["title"] if t))[:5],
            "f4_periods": [min(m["date"]), max(m["date"])] if len(m) else []}


for i, ((ctx, kfl), g) in enumerate(grpk):
    g = g.sort_values("date")
    a, b = g.iloc[0], g.iloc[-1]
    emit("K", a, b, {"anchor": f4_anchor(ctx, kfl), "group_names": sorted(set(g["raw_name"])),
                     "group_events": [(r.date, r.event_type, r.title) for r in g.itertuples()][:8],
                     "r17_labelled": i < 140})

# ---------- X: 8-K vs Form 3/4/5 person owner, census of all rows -------------------------------
repx = k8.sort_values(["date", "rec_id"]).drop_duplicates(["ctx", "k_full"])
cands = []
for r in repx.itertuples():
    g = f4_by_issuer.get(r.ctx)
    if g is None:
        continue
    m = g[g["k_fl"] == r.k_fl]
    if len(m):
        cands.append((r, m))
cands.sort(key=lambda rm: (0 if rm[1]["xref"].nunique() > 1 else 1, h(rm[0].rec_id)))
print("X rows with a same-issuer Form 3/4/5 fl anchor (census):", len(cands),
      "| research 17 labelled the first 140")

# Per (issuer, owner CIK): every Form 3/4/5 row that CIK filed at that issuer, in period order.
# `f4_forms_this_cik` is what L-21A/L-21C need -- whether the earliest row is a Form 3 (which
# dates the start of the insider relationship) or a Form 4 (which presupposes an earlier Form 3).
by_ctx_cik = {k: g.sort_values("date") for k, g in f4p.groupby(["ctx", "xref"])}
k8_by_ctx_key = {k: g.sort_values("date") for k, g in k8.groupby(["ctx", "k_full"])}

for i, (r, m) in enumerate(cands):
    m = m.sort_values("date")
    for x, gm in m.groupby("xref"):
        b = gm.iloc[0]
        allrows = by_ctx_cik[(r.ctx, x)]
        emit("X", r, b, {"f4_ciks_with_fl": sorted(set(m["xref"])),
                         "f4_names": sorted(set(gm["raw_name"])),
                         "f4_all_names_this_cik": sorted(set(allrows["raw_name"])),
                         "f4_flags": sorted(set(gm["flag_combo"])),
                         "f4_titles": sorted(set(t for t in gm["title"] if t))[:5],
                         "f4_periods": [min(gm["date"]), max(gm["date"])],
                         "f4_all_periods_this_cik": [str(allrows["date"].iloc[0]), str(allrows["date"].iloc[-1])],
                         "f4_forms_this_cik": list(allrows["schedule"]),
                         "f4_n_rows_this_cik": int(len(allrows)),
                         "src_events": [(q.date, q.event_type, q.title) for q in
                                        k8_by_ctx_key[(r.ctx, r.k_full)].itertuples()][:6],
                         "r17_labelled": i < 140})

# ---------- bridge census (hard case 3), 8-K side -----------------------------------------------
# A transitive bridge needs a third key value between two others: a (issuer, surname+first
# initial) group holding >= 3 distinct `full` keys. Counted over 8-K alone and over 8-K union the
# Form 3/4/5 person owners at the same issuer, which is the cross-source chain the X stratum
# could produce.
bridge = {"8k_only": [], "8k_plus_f4": []}
rep8 = k8.sort_values(["date", "rec_id"]).drop_duplicates(["ctx", "k_full"])
for (ctx, blk), g in rep8.groupby(["ctx", "block"]):
    if g["k_full"].nunique() >= 3:
        bridge["8k_only"].append({"ctx": ctx, "block": blk, "names": sorted(set(g["raw_name"]))})
both = pd.concat([rep8.assign(src="8k"),
                  f4p.sort_values(["date", "rec_id"]).drop_duplicates(["ctx", "k_full"]).assign(src="f4")])
for (ctx, blk), g in both.groupby(["ctx", "block"]):
    if g["k_full"].nunique() >= 3 and set(g["src"]) == {"8k", "f4"}:
        bridge["8k_plus_f4"].append({"ctx": ctx, "block": blk,
                                     "names": sorted(set(g["raw_name"])),
                                     "mi_keys": sorted(set(g["k_mi"])),
                                     "srcs": sorted(set(g["src"]))})
print("bridge groups: 8-K only", len(bridge["8k_only"]), "| 8-K + F4", len(bridge["8k_plus_f4"]))

c21.R21.mkdir(exist_ok=True)
with open(c21.R21 / "pairs_draft.jsonl", "w") as f:
    for p in pairs:
        f.write(json.dumps(p, default=str) + "\n")
with open(c21.R21 / "bridges.json", "w") as f:
    json.dump(bridge, f, indent=1, default=str)

print(Counter(p["stratum"] for p in pairs))
print("pairs matching the fixed key:", sum(1 for p in pairs if p["key_fixed"]),
      "| matching `mi` alone:", sum(1 for p in pairs if p["match"]["mi"]),
      "| suffix-vetoed among `mi` matches:",
      sum(1 for p in pairs if p["match"]["mi"] and p["suffix_veto"]))
print("already labelled by research 17:", sum(1 for p in pairs if p.get("r17_labelled")))
