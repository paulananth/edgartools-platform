"""Research 17, stage 4: score the compound context key per source and normalizer variant.

Reads 17-census.json (population counts) and 17-pairs.jsonl (labels), writes 17-summary.json.

Two precision framings per source:
  population  -- P(same person | two records share ctx + key_V), unit = multi-record key group in the
                 whole corpus; a group is impure if any labelled id-pair inside it is `different`
                 (pessimistic also counts `unknown` as impure). This is what Tier B faces on a source
                 with no cross-reference id (8-K, DEF 14A) and what the key delivers before Tier A.
  residual    -- P(same person | key_V matches AND the cross-reference ids differ), unit = labelled
                 id-pair (stratum H). This is the population Tier B actually decides on for ADV and
                 Form 3/4/5 once Tier A has bound every shared id.
Wilson lower bounds at one-sided 95% (z=1.645, Clean MDM accepted Q11) and 97.5% (z=1.960,
research 18's constant).
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

spec = importlib.util.spec_from_file_location("c17", Path(__file__).with_name("17-common.py"))
c17 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(c17)

census = json.load(open(c17.HERE / "17-census.json"))
pairs = [json.loads(l) for l in open(c17.HERE / "17-pairs.jsonl")]
V = c17.VARIANTS


def wl(k, n):
    return {"lcb95": round(c17.wilson_lower(k, n, c17.Z95), 5) if n else None,
            "lcb975": round(c17.wilson_lower(k, n, c17.Z975), 5) if n else None}


def prec_block(same, diff, unk):
    n = same + diff + unk
    out = {"n": n, "same": same, "different": diff, "unknown": unk}
    if n:
        out["precision_pessimistic"] = round(same / n, 5)
        out["precision_optimistic"] = round((same + unk) / n, 5)
        out["pessimistic"] = wl(same, n)
        out["optimistic"] = wl(same + unk, n)
        out["settled_only"] = {"n": same + diff, "precision": round(same / (same + diff), 5) if same + diff else None,
                               **(wl(same, same + diff) if same + diff else {})}
    return out


summary = {"run_et": datetime.now(ZoneInfo("America/New_York")).isoformat(timespec="seconds"),
           "wilson": census["wilson"], "sources": {}, "hard_cases": {}, "strata": {}}

# ---- strata counts ------------------------------------------------------------------------------------
cnt = Counter((p["stratum"], p["source"], p["label"]) for p in pairs)
summary["strata"]["counts"] = {f"{s}|{src}|{l}": c for (s, src, l), c in sorted(cnt.items())}
summary["strata"]["rules"] = dict(Counter(p["labeler_rule"] for p in pairs))
summary["strata"]["total_pairs"] = len(pairs)
summary["strata"]["overrides"] = sum(1 for p in pairs if "override" in p["evidence"])

# ---- per source -------------------------------------------------------------------------------------------
for src, census_key in (("adv", "adv"), ("f4", "f4_person"), ("8k", "8k"), ("proxy", "proxy")):
    cs = census["sources"][census_key]
    S = {"records": cs["records"], "person_shaped": cs["person_shaped"], "xref_present": cs["xref_present"],
         "xref_blank": cs["xref_blank"], "distinct_ctx": cs["distinct_ctx"], "distinct_xref": cs["distinct_xref"],
         "not_eligible_per_1000": round(1000 * (cs["records"] - cs["person_shaped"]) / cs["records"], 2),
         "variants": {}}
    for v in V:
        cv = cs["variants"][v]
        d = {"groups_multi_record": cv["groups_multi_record"], "records_in_multi_groups": cv["records_in_multi_groups"],
             "decisions": cv["records_in_multi_groups"] - cv["groups_multi_record"],
             "review_per_1000": cv["review_per_1000"], "records_block_cand_no_key_cand": cv["records_block_cand_no_key_cand"]}
        if src in ("adv", "f4"):
            d["groups_with_2plus_xref"] = cv["groups_with_2plus_xref"]
            d["groups_with_xref_and_blank"] = cv["groups_with_2plus_xref_and_blank"]
            d["recall_id_groups"] = cv["recall_id_groups"]
            d["id_groups_multi"] = cv["id_groups_multi"]
            d["id_groups_key_split"] = cv["id_groups_key_split"]
            # residual: H pairs matching under v (any record pair of the two ids)
            H = [p for p in pairs if p["stratum"] == "H" and p["source"] == src and p["any_match"][v]]
            lab = Counter(p["label"] for p in H)
            d["residual"] = prec_block(lab["same"], lab["different"], lab["unknown"])
            # population: groups under v. Impure groups = distinct (ctx, key_v) groups holding a `different`
            # pair; unknown groups likewise. Use the pair's a-side key_v to locate the group.
            grp_state = {}
            for p in H:
                ka = p["a"].get("k_" + v) if "k_" + v in p["a"] else None
                gid = (p["ctx"], p["key_fields"]["a_name"] if ka is None else ka)
                st = grp_state.get(gid, "same")
                if p["label"] == "different":
                    st = "different"
                elif p["label"] == "unknown" and st != "different":
                    st = "unknown"
                grp_state[gid] = st
            imp = Counter(grp_state.values())
            n_groups = cv["groups_multi_record"]
            pure = n_groups - imp["different"] - imp["unknown"]
            d["population"] = prec_block(pure, imp["different"], imp["unknown"])
            d["population"]["note"] = ("unit = multi-record (ctx, key) group; groups with one id are pure by the id "
                                       "label (see Limits: id labels are partly name-derived)")
        else:
            # 8-K / proxy: labelled K (within) and X (cross-source) pairs matching under v
            K = [p for p in pairs if p["stratum"] == "K" and p["source"] == src and p["match"][v]]
            X = [p for p in pairs if p["stratum"] == "X" and p["source"] == src and p["match"][v]]
            for name, P in (("within_source", K), ("cross_source_vs_f4", X)):
                lab = Counter(p["label"] for p in P)
                d[name] = prec_block(lab["same"], lab["different"], lab["unknown"])
                d[name]["rules"] = dict(Counter(p["labeler_rule"] for p in P))
            both = K + X
            lab = Counter(p["label"] for p in both)
            d["pooled"] = prec_block(lab["same"], lab["different"], lab["unknown"])
            # anchored-only view (labels resting on a Form 3/4/5 CIK or a middle-name conflict, not on continuity)
            anch = [p for p in both if p["labeler_rule"].split()[0] in ("L-K1", "L-K3", "L-X1", "L-X4", "L-H1")]
            lab = Counter(p["label"] for p in anch)
            d["anchored_only"] = prec_block(lab["same"], lab["different"], lab["unknown"])
        # role element: how many key-matching labelled pairs have inconsistent roles, and what labels they carry
        allp = [p for p in pairs if p["source"] == src and p["stratum"] in ("H", "K", "X", "P") and (p.get("any_match", p["match"])[v])]
        rc = Counter((p["roles_consistent"], p["label"]) for p in allp)
        d["role_consistency"] = {f"{'consistent' if k[0] else 'inconsistent'}|{k[1]}": c for k, c in sorted(rc.items())}
        S["variants"][v] = d
    summary["sources"][src] = S

# ---- hard cases -----------------------------------------------------------------------------------------------
hc = {}
for src in ("adv", "f4"):
    H = [p for p in pairs if p["stratum"] == "H" and p["source"] == src]
    hc[f"homonyms_{src}"] = {
        "id_pairs_same_ctx_same_fl": len(H),
        "by_variant": {v: dict(Counter(p["label"] for p in H if p["any_match"][v])) for v in V},
        "rules": dict(Counter(p["labeler_rule"] for p in H)),
        "iapd_settled": sum(1 for p in H if p["labeler_rule"].startswith(("L-H3", "L-H7", "L-H8"))),
    }
    R = [p for p in pairs if p["stratum"] == "R" and p["source"] == src]
    hc[f"reused_ids_{src}"] = {"id_split_pairs": len(R), "labels": dict(Counter(p["label"] for p in R)),
                               "rules": dict(Counter(p["labeler_rule"] for p in R)),
                               "captured_by_variant": {v: sum(1 for p in R if p["match"][v]) for v in V},
                               "unexplained": [{"id": p["a"]["xref"], "names": [p["a"]["raw_name"], p["b"]["raw_name"]], "label": p["label"], "evidence": p["evidence"][:200]}
                                               for p in R if p["label"] != "same"]}
B = [p for p in pairs if p["stratum"] == "B"]
hc["bridges"] = {
    "fl_groups_with_3plus_full_keys": 0,
    "note": "no (ctx, last|first) group in any source holds three distinct full keys, so no A~B~C chain exists "
            "under the exact-equality key; bridges were constructed at the Tier C comparator (surname + first initial)",
    "block_groups_with_3plus_full_keys": dict(Counter(p["source"] for p in B if True)),
    "pairs": len(B), "labels": dict(Counter((p["source"], p["label"]) for p in B).items()) if False else {f"{s}|{l}": c for (s, l), c in Counter((p["source"], p["label"]) for p in B).items()},
    "fl_equal_pairs_inside_block_groups": {f"{s}|{l}": c for (s, l), c in Counter((p["source"], p["label"]) for p in B if p["match"]["fl"]).items()},
}
summary["hard_cases"] = hc

# 8-K eligibility detail
k8 = census["sources"]["8k"]
summary["sources"]["8k"]["eligibility"] = {"records": k8["records"], "person_shaped_no_role_text": k8["person_shaped"],
                                           "share_eligible": round(k8["person_shaped"] / k8["records"], 4)}
px = census["sources"]["proxy"]
summary["sources"]["proxy"]["eligibility"] = {"records": px["records"], "person_shaped_no_role_text": px["person_shaped"],
                                              "share_eligible": round(px["person_shaped"] / px["records"], 4)}
summary["adv_firm_cik_bridge"] = census["adv_firm_cik_bridge"]
summary["inputs"] = census["inputs"]
summary["inputs"]["17-pairs.jsonl"] = {"sha256": c17.sha256_file(c17.HERE / "17-pairs.jsonl")}
summary["inputs"]["17-iapd-results.jsonl"] = {"sha256": c17.sha256_file(c17.HERE / "17-iapd-results.jsonl")}
summary["inputs"]["17-iapd-requests.jsonl"] = {"sha256": c17.sha256_file(c17.HERE / "17-iapd-requests.jsonl"),
                                                "requests": sum(1 for _ in open(c17.HERE / "17-iapd-requests.jsonl"))}
with open(c17.HERE / "17-summary.json", "w") as f:
    json.dump(summary, f, indent=1)
print(json.dumps({s: {v: {k: d[v].get(k) for k in ("residual", "population", "within_source", "cross_source_vs_f4", "pooled", "anchored_only", "review_per_1000", "recall_id_groups") if d[v].get(k) is not None}
                       for v, d in [(v, summary["sources"][s]["variants"]) for v in V]} for s in summary["sources"]}, indent=1)[:6000])
