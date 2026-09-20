"""Research 17, stage 2: enumerate candidate pairs per stratum and write the draft pair file
(scratchpad r17/pairs_draft.jsonl) plus compact review sheets (r17/review_*.txt).

Strata (pair = two *records* from different filings at the same firm/issuer):
  H  homonym candidates: same ctx, same `fl` key, DIFFERENT cross-ref id (ADV OwnerID / F4 owner_cik)
     -- a census, every such id pair, tagged with which variants (full/nosuffix/mi/fl) also match
  R  id-split: same ctx, same cross-ref id, different `full` key (name variant / reused id)
     -- census; recall of the key and the 'reused id' hard case
  B  bridges: `fl` groups whose members carry >= 3 distinct `full` keys (A~B~C under fl, A != C under full)
     -- census
  P  random same-ctx same-`full`-key pairs with a cross-ref id on both sides (ADV, F4) -- id-labelled,
     corroborated by an id-independent field
  K  8-K within-source: same issuer, same `fl` key, two 8-K rows -- hand-labelled
  X  cross-source: 8-K / proxy row vs F4 person owner at the same issuer, same `fl` key -- hand-labelled
"""
from __future__ import annotations

import hashlib
import importlib.util
import itertools
import json
import random
from collections import defaultdict
from pathlib import Path

import pandas as pd

spec = importlib.util.spec_from_file_location("c17", Path(__file__).with_name("17-common.py"))
c17 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(c17)

rec = pd.read_parquet(c17.R17 / "records.parquet")
rec = rec[rec["shape"]].copy()
rec["roles_set"] = rec["roles"].map(lambda s: set(x for x in s.split("|") if x))
f4p = rec[(rec["source"] == "f4") & (rec["event_type"] == "person")]
adv = rec[rec["source"] == "adv"]
k8 = rec[rec["source"] == "8k"]
px = rec[rec["source"] == "proxy"]

rng = random.Random(c17.SEED)
pairs: list[dict] = []


def h(*parts) -> str:
    return hashlib.sha256("|".join(map(str, parts)).encode()).hexdigest()[:12]


def side(r) -> dict:
    return {"rec_id": r.rec_id, "raw_name": r.raw_name, "xref": r.xref, "filing": r.filing,
            "month": r.month, "title": r.title, "roles": r.roles, "acquired": r.acquired,
            "own_code": r.own_code, "control": r.control, "schedule": r.schedule, "sub": r.sub,
            "event_type": r.event_type, "date": r.date, "flag_combo": r.flag_combo,
            "k_full": r.k_full, "k_nosuffix": r.k_nosuffix, "k_mi": r.k_mi, "k_fl": r.k_fl}


def variant_matches(a, b) -> dict:
    return {v: bool(getattr(a, f"k_{v}") == getattr(b, f"k_{v}")) for v in c17.VARIANTS}


def emit(stratum, source, a, b, extra=None):
    vm = variant_matches(a, b)
    d = {"pair_id": f"{stratum}-{source}-{h(a.rec_id, b.rec_id)}", "stratum": stratum, "source": source,
         "ctx": a.ctx, "firm_name": a.firm_name or b.firm_name,
         "key_fields": {"ctx": a.ctx, "a_name": a.raw_name, "b_name": b.raw_name,
                        "a_roles": a.roles, "b_roles": b.roles},
         "match": vm, "roles_consistent": c17.roles_consistent(a.roles_set, b.roles_set),
         "a": side(a), "b": side(b), "label": "", "evidence": "", "labeler_rule": ""}
    if extra:
        d.update(extra)
    pairs.append(d)
    return d


def representative(df: pd.DataFrame) -> pd.DataFrame:
    """One record per (ctx, xref, full key): the earliest filing, so a pair is two records."""
    return df.sort_values(["filing", "rec_id"]).drop_duplicates(["ctx", "xref", "k_full"])


# ---------- H: homonym candidates (different id, same fl key at the same ctx) ----------------------
for src, df in (("adv", adv), ("f4", f4p)):
    lab = df[df["xref"] != ""]
    rep = representative(lab)
    for (ctx, kfl), g in rep.groupby(["ctx", "k_fl"]):
        ids = sorted(g["xref"].unique())
        if len(ids) < 2:
            continue
        # one pair per id pair, using each id's first representative record
        first = {x: g[g["xref"] == x].iloc[0] for x in ids}
        for x, y in itertools.combinations(ids, 2):
            a, b = first[x], first[y]
            # also note whether any other record pair of the two ids matches under full
            ga, gb = g[g["xref"] == x], g[g["xref"] == y]
            any_full = bool(set(ga["k_full"]) & set(gb["k_full"]))
            any_mi = bool(set(ga["k_mi"]) & set(gb["k_mi"]))
            any_ns = bool(set(ga["k_nosuffix"]) & set(gb["k_nosuffix"]))
            d = emit("H", src, a, b, {"any_match": {"full": any_full, "nosuffix": any_ns, "mi": any_mi, "fl": True},
                                       "a_names": sorted(set(ga["raw_name"])), "b_names": sorted(set(gb["raw_name"])),
                                       "a_titles": sorted(set(ga["title"]))[:6], "b_titles": sorted(set(gb["title"]))[:6],
                                       "a_acquired": sorted(set(ga["acquired"]))[:6], "b_acquired": sorted(set(gb["acquired"]))[:6],
                                       "a_flags": sorted(set(ga["flag_combo"])), "b_flags": sorted(set(gb["flag_combo"])),
                                       "a_months": sorted(set(ga["month"])), "b_months": sorted(set(gb["month"]))})

# ---------- R: id-split (same id, same ctx, different full key) ------------------------------------------
for src, df in (("adv", adv), ("f4", f4p)):
    lab = df[df["xref"] != ""]
    agg = lab.groupby(["ctx", "xref", "k_full"]).agg(titles=("title", lambda s: sorted(set(s))[:6]),
                                                     acquired=("acquired", lambda s: sorted(set(s))[:6]),
                                                     months=("month", lambda s: sorted(set(s)))).to_dict("index")
    rep = representative(lab)
    for (ctx, x), g in rep.groupby(["ctx", "xref"]):
        if g["k_full"].nunique() < 2:
            continue
        g = g.sort_values("k_full")
        a = g.iloc[0]
        for i in range(1, len(g)):
            b = g.iloc[i]
            ea, eb = agg[(ctx, x, a.k_full)], agg[(ctx, x, b.k_full)]
            emit("R", src, a, b, {"a_titles": ea["titles"], "b_titles": eb["titles"], "a_acquired": ea["acquired"],
                                  "b_acquired": eb["acquired"], "a_months": ea["months"], "b_months": eb["months"]})

# ---------- B: bridges ---------------------------------------------------------------------------------------------
bridges = []
for src, df in (("adv", adv), ("f4", f4p), ("8k", k8), ("proxy", px)):
    rep = df.sort_values(["filing", "rec_id"]).drop_duplicates(["ctx", "xref", "k_full"]) if src in ("adv", "f4") \
        else df.sort_values(["filing", "rec_id"]).drop_duplicates(["ctx", "k_full"])
    for (ctx, kfl), g in rep.groupby(["ctx", "block"]):
        fulls = sorted(g["k_full"].unique())
        if len(fulls) < 3:
            continue
        # a bridge needs a member that fl-matches two members which do not full-match each other:
        # with exact-equality keys every member of an fl group matches every other, so the
        # chain is A(full1) ~ B(full2) ~ C(full3). Record the group; ids tell whether A and C are one person.
        ids = sorted(set(g.loc[g["xref"] != "", "xref"]))
        bridges.append({"source": src, "ctx": ctx, "block": kfl, "n_full_keys": len(fulls), "n_fl_keys": int(g["k_fl"].nunique()),
                        "full_keys": fulls, "names": sorted(set(g["raw_name"])), "ids": ids,
                        "n_ids": len(ids), "titles": sorted(set(g["title"]))[:8],
                        "months": sorted(set(g["month"]))})
        # emit the two "ends": the two full keys that differ most (first and last alphabetically)
        # and the hub (a key with an empty middle if one exists, else the second)
        # every pair of distinct full keys inside the block group is a candidate the Tier C comparator raises
        firsts = {k: g[g["k_full"] == k].iloc[0] for k in fulls}
        for ka, kc in itertools.combinations(fulls, 2):
            emit("B", src, firsts[ka], firsts[kc], {"bridge_full_keys": fulls, "bridge_ids": ids, "bridge_names": sorted(set(g["raw_name"])),
                                                    "bridge_fl_keys": sorted(set(g["k_fl"]))})

# ---------- P: random same-full-key pairs, id on both sides ------------------------------------------------------
for src, df, n in (("adv", adv, 160), ("f4", f4p, 110)):
    lab = df[df["xref"] != ""]
    # candidate groups: same ctx + same full key with >= 2 distinct filings
    rep = lab.sort_values(["filing", "rec_id"]).drop_duplicates(["ctx", "k_full", "filing"])
    grp = [(k, g) for k, g in rep.groupby(["ctx", "k_full"]) if len(g) >= 2]
    grp.sort(key=lambda kg: h(*kg[0]))
    picked = grp[:n]
    for (ctx, kf), g in picked:
        g = g.sort_values("filing")
        a = g.iloc[0]
        # prefer a partner from the other month (ADV) / a later period (F4) so the pair spans filings
        other = g[g["month"] != a.month]
        b = other.iloc[0] if len(other) else g.iloc[1]
        emit("P", src, a, b)

# ---------- K: 8-K within-source pairs (same issuer, same fl key) ----------------------------------------------------
rep = k8.sort_values(["date", "rec_id"]).drop_duplicates(["ctx", "k_full", "filing"])
grp = [(k, g) for k, g in rep.groupby(["ctx", "k_fl"]) if len(g) >= 2 and g["date"].nunique() >= 2]
grp.sort(key=lambda kg: h(*kg[0]))
print("8k within-source groups with >=2 dates:", len(grp))
# F4 anchor info for the issuer
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


for (ctx, kfl), g in grp[:140]:
    g = g.sort_values("date")
    a, b = g.iloc[0], g.iloc[-1]
    emit("K", "8k", a, b, {"anchor": f4_anchor(ctx, kfl), "group_names": sorted(set(g["raw_name"])),
                           "group_events": [(r.date, r.event_type, r.title) for r in g.itertuples()][:8]})

# ---------- X: cross-source (8-K or proxy row) vs F4 person owner at the same issuer -----------------------------
for src, df, n in (("8k", k8, 140), ("proxy", px, 70)):
    rep = df.sort_values(["date", "rec_id"]).drop_duplicates(["ctx", "k_full"])
    cands = []
    for r in rep.itertuples():
        g = f4_by_issuer.get(r.ctx)
        if g is None:
            continue
        m = g[g["k_fl"] == r.k_fl]
        if not len(m):
            continue
        cands.append((r, m))
    cands.sort(key=lambda rm: (0 if rm[1]["xref"].nunique() > 1 else 1, h(rm[0].rec_id)))
    stats = {"rows_with_f4_issuer": int(rep["ctx"].isin(f4_by_issuer.keys()).sum()), "rows_with_fl_anchor": len(cands),
             "rows_with_2plus_ciks": sum(1 for r, m in cands if m["xref"].nunique() > 1)}
    print(src, "cross-source", stats)
    for r, m in cands[:n]:
        m = m.sort_values("date")
        # one F4 side per distinct CIK (usually one)
        for x, gm in m.groupby("xref"):
            b = gm.iloc[0]
            emit("X", src, r, b, {"f4_ciks_with_fl": sorted(set(m["xref"])), "f4_names": sorted(set(gm["raw_name"])),
                                  "f4_flags": sorted(set(gm["flag_combo"])), "f4_titles": sorted(set(t for t in gm["title"] if t))[:5],
                                  "f4_periods": [min(gm["date"]), max(gm["date"])],
                                  "src_events": [(q.date, q.event_type, q.title) for q in df[(df.ctx == r.ctx) & (df.k_full == r.k_full)].sort_values("date").itertuples()][:6]})

with open(c17.R17 / "pairs_draft.jsonl", "w") as f:
    for p in pairs:
        f.write(json.dumps(p, default=str) + "\n")
with open(c17.R17 / "bridges.json", "w") as f:
    json.dump(bridges, f, indent=1, default=str)

from collections import Counter
print(Counter((p["stratum"], p["source"]) for p in pairs))
print("bridges", Counter(b["source"] for b in bridges))

# ---------- review sheets ----------------------------------------------------------------------------------------
def sheet(stratum, src, fn):
    with open(c17.R17 / f"review_{stratum}_{src}.txt", "w") as f:
        for p in pairs:
            if p["stratum"] == stratum and p["source"] == src:
                f.write(fn(p) + "\n")


def fmt_h(p):
    a, b = p["a"], p["b"]
    return (f"{p['pair_id']} ctx={p['ctx']} [{p['firm_name'][:40]}] any_full={p['any_match']['full']} mi={p['any_match']['mi']}\n"
            f"   A id={a['xref']} names={p['a_names']} titles={p['a_titles']} acq={p['a_acquired']} flags={p['a_flags']} months={p['a_months']} sched={a['schedule']} own={a['own_code']} ctl={a['control']}\n"
            f"   B id={b['xref']} names={p['b_names']} titles={p['b_titles']} acq={p['b_acquired']} flags={p['b_flags']} months={p['b_months']} sched={b['schedule']} own={b['own_code']} ctl={b['control']}")


def fmt_r(p):
    a, b = p["a"], p["b"]
    return (f"{p['pair_id']} ctx={p['ctx']} [{p['firm_name'][:40]}] id={a['xref']} match={ {k: v for k, v in p['match'].items() if v} }\n"
            f"   A '{a['raw_name']}' titles={p['a_titles']} acq={p['a_acquired']} months={p['a_months']} flags={a['flag_combo']}\n"
            f"   B '{b['raw_name']}' titles={p['b_titles']} acq={p['b_acquired']} months={p['b_months']} flags={b['flag_combo']}")


def fmt_b(p):
    a, b = p["a"], p["b"]
    return (f"{p['pair_id']} ctx={p['ctx']} [{p['firm_name'][:40]}] A id={a['xref']} '{a['raw_name']}' t='{a['title'][:30]}' acq={a['acquired']} fl={a['flag_combo']} | B id={b['xref']} '{b['raw_name']}' t='{b['title'][:30]}' acq={b['acquired']} fl={b['flag_combo']} | group ids={p['bridge_ids']} names={p['bridge_names']}")


def fmt_p(p):
    a, b = p["a"], p["b"]
    return (f"{p['pair_id']} ctx={p['ctx']} [{p['firm_name'][:40]}] A id={a['xref']} '{a['raw_name']}' t='{a['title'][:30]}' acq={a['acquired']} m={a['month']} fl={a['flag_combo']} | "
            f"B id={b['xref']} '{b['raw_name']}' t='{b['title'][:30]}' acq={b['acquired']} m={b['month']} fl={b['flag_combo']}")


def fmt_k(p):
    a, b = p["a"], p["b"]
    return (f"{p['pair_id']} issuer={p['ctx']} names={p['group_names']} events={p['group_events']}\n   anchor={p['anchor']}")


def fmt_x(p):
    a, b = p["a"], p["b"]
    return (f"{p['pair_id']} issuer={p['ctx']} SRC '{a['raw_name']}' events={p['src_events']}\n"
            f"   F4 cik={b['xref']} names={p['f4_names']} flags={p['f4_flags']} titles={p['f4_titles']} periods={p['f4_periods']} ciks_with_fl={p['f4_ciks_with_fl']}")


for st, src, fn in (("H", "adv", fmt_h), ("H", "f4", fmt_h), ("R", "adv", fmt_r), ("R", "f4", fmt_r),
                    ("B", "adv", fmt_b), ("B", "f4", fmt_b), ("B", "8k", fmt_b), ("B", "proxy", fmt_b),
                    ("P", "adv", fmt_p), ("P", "f4", fmt_p), ("K", "8k", fmt_k), ("X", "8k", fmt_x), ("X", "proxy", fmt_x)):
    sheet(st, src, fn)
