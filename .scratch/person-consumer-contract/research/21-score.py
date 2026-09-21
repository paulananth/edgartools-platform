"""Research 21, stage 3: score the fixed Tier B key on the 8-K Item 5.02 census.

Reads `21-pairs.jsonl` (this study's labels) and `17-pairs.jsonl` (research 17's, for the pooled
view and to identify which pairs are new), plus `r17/records.parquet` for the population counts
that review volume and recall need. Writes `21-summary.json`.

Three readings of every precision cell, because `unknown` answers a different question from
`different`:
  optimistic   -- every `unknown` is a correct merge  (an upper bound; ticket 20 Q2's reading)
  conservative -- every `unknown` (and every `ineligible`) is an error  (a lower bound)
  settled      -- unknowns dropped: same / (same + different)  (precision among pairs that carry
                  evidence; the denominator is what n >= 381 has to be measured on)

Wilson lower bounds at one-sided 95% (z = 1.6448536) and one-sided 97.5% (z = 1.9599640), using
research 17's `wilson_lower` unchanged.

Run: uv run --no-project --with pandas --with pyarrow python 21-score.py
"""
from __future__ import annotations

import importlib.util
import json
from collections import Counter
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd

_spec = importlib.util.spec_from_file_location("c21", Path(__file__).with_name("21-common.py"))
c21 = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(c21)
c17 = c21.c17

P = [json.loads(l) for l in open(c21.HERE / "21-pairs.jsonl")]
R17 = [json.loads(l) for l in open(c21.HERE / "17-pairs.jsonl")]
r17_8k = [p for p in R17 if p["source"] == "8k" and p["stratum"] in ("K", "X")]
r17_ids = {p["pair_id"] for p in r17_8k}


def wl(k, n):
    return {"lcb95": round(c17.wilson_lower(k, n, c17.Z95), 5) if n else None,
            "lcb975": round(c17.wilson_lower(k, n, c17.Z975), 5) if n else None}


def block(pairs: list[dict]) -> dict:
    c = Counter(p["label"] for p in pairs)
    same, diff, unk, inel = c["same"], c["different"], c["unknown"], c["ineligible"]
    n_all = same + diff + unk + inel
    out = {"n_candidates": n_all, "same": same, "different": diff, "unknown": unk,
           "ineligible": inel}
    if not n_all:
        return out
    # eligible denominator: `ineligible` rows are not persons and never reach a tier
    n = same + diff + unk
    out["n"] = n
    out["optimistic"] = {"precision": round((same + unk) / n, 5) if n else None, **wl(same + unk, n)}
    out["conservative"] = {"precision": round(same / n_all, 5),
                           **wl(same, n_all),
                           "note": "unknown AND ineligible both counted as errors"}
    out["conservative_eligible"] = {"n": n, "precision": round(same / n, 5) if n else None,
                                    **wl(same, n),
                                    "note": "unknown counted as an error; `ineligible` rows "
                                            "dropped, since a row that is not a person never "
                                            "reaches a tier and cannot be a merge error"}
    out["settled"] = {"n": same + diff,
                      "precision": round(same / (same + diff), 5) if same + diff else None,
                      **(wl(same, same + diff) if same + diff else {})}
    return out


summary = {"run_et": datetime.now(ZoneInfo("America/New_York")).isoformat(timespec="seconds"),
           "wilson": {"z_one_sided_95": c17.Z95, "z_one_sided_975": c17.Z975,
                      "n_zero_errors_for_0.99_at_95": c21.n_for_lcb(0.99, c17.Z95),
                      "n_zero_errors_for_0.99_at_975": c21.n_for_lcb(0.99, c17.Z975),
                      "n_one_error_for_0.99_at_975": c21.n_for_lcb(0.99, c17.Z975, 1),
                      "n_two_errors_for_0.99_at_975": c21.n_for_lcb(0.99, c17.Z975, 2)},
           "census": {"candidate_pairs": len(P),
                      "K_within_source": sum(1 for p in P if p["stratum"] == "K"),
                      "X_cross_source": sum(1 for p in P if p["stratum"] == "X"),
                      "already_labelled_by_r17": sum(1 for p in P if p["pair_id"] in r17_ids),
                      "new_in_r21": sum(1 for p in P if p["pair_id"] not in r17_ids)}}

FIXED = [p for p in P if p["key_fixed"]]

# ---- headline: the fixed key ---------------------------------------------------------------
summary["fixed_key"] = {
    "definition": "same issuer CIK + surname|given name|middle initial (`mi`) + no generational-"
                  "suffix conflict (JR/SR/II/III/IV present on one side only, or conflicting, is "
                  "a veto). Ticket 20 Q3.",
    "pooled": block(FIXED),
    "new_pairs_only": block([p for p in FIXED if p["pair_id"] not in r17_ids]),
    "r17_pairs_only": block([p for p in FIXED if p["pair_id"] in r17_ids]),
    "by_stratum": {s: block([p for p in FIXED if p["stratum"] == s]) for s in ("K", "X")},
}

# ---- comparison variants (context only; ticket 20 fixed the key) ------------------------------
summary["variants_for_comparison"] = {}
for v in c17.VARIANTS:
    summary["variants_for_comparison"][v] = block([p for p in P if p["match"][v]])
summary["variants_for_comparison"]["mi_without_the_suffix_veto"] = block([p for p in P if p["match"]["mi"]])

# ---- label-evidence classes ---------------------------------------------------------------
# `anchored` = the label rests on an external Form 3/4/5 filer CIK at the same issuer, or on a
# name conflict, not on my reading of the 8-K event sequence.
ANCHORED = ("L-K1", "L-X1", "L-X2", "L-X4", "L-K3", "L-H1", "L-21A", "L-21B", "L-21C", "L-21E",
            "L-21F")
CONTINUITY = ("L-K5", "L-K6", "L-K7", "L-K8", "L-K2", "L-K4")


def rule0(p):
    return p["labeler_rule"].split()[0]


anch = [p for p in FIXED if rule0(p) in ANCHORED and p["stratum"] == "X"]
summary["evidence_classes"] = {
    "anchored_external_cik_only": {**block(anch),
                                   "note": "every pair whose label rests on a Form 3/4/5 filer "
                                           "CIK at the same issuer; excludes every within-8-K "
                                           "timeline-continuity label"},
    "within_8k_continuity_only": block([p for p in FIXED if rule0(p) in CONTINUITY]),
    "rules": dict(Counter(rule0(p) for p in FIXED)),
    "rules_new_pairs": dict(Counter(rule0(p) for p in FIXED if p["pair_id"] not in r17_ids)),
}

# ---- hard-case strata ------------------------------------------------------------------------
rec = pd.read_parquet(c21.R17 / "records.parquet")
rec = rec[rec["shape"]]
k8 = rec[rec["source"] == "8k"]
f4p = rec[(rec["source"] == "f4") & (rec["event_type"] == "person")]

# H: homonym risk at one issuer -- (issuer, surname+first-initial) blocks holding >= 2 distinct
# `full` keys on the 8-K side, and the X pairs where >= 2 Form 3/4/5 CIKs carry the `fl` key.
blk = k8.drop_duplicates(["ctx", "k_full"]).groupby(["ctx", "block"])["k_full"].nunique()
hom_blocks = set(blk[blk >= 2].index)
hom_pairs = [p for p in FIXED if (p["ctx"], p["a"]["raw_name"] and
                                  c17.block_key(c17.parse_western(p["key_fields"]["a_name"]))) in hom_blocks]
two_cik = [p for p in FIXED if len(p.get("f4_ciks_with_fl") or []) > 1]
# R: the 8-K-facing analogue of a reused identifier -- the anchoring Form 3/4/5 CIK carries more
# than one distinct name at that issuer.
reused = [p for p in FIXED if len(p.get("f4_all_names_this_cik") or []) > 1]
bridges = json.load(open(c21.R21 / "bridges.json"))
summary["hard_cases"] = {
    "homonyms_same_issuer": {
        "8k_blocks_with_2plus_full_keys": int((blk >= 2).sum()),
        "8k_blocks_total": int(len(blk)),
        "pairs_from_those_blocks": block(hom_pairs),
        "x_pairs_with_2plus_f4_ciks": block(two_cik),
        "x_rows_with_2plus_f4_ciks": sum(1 for p in P if len(p.get("f4_ciks_with_fl") or []) > 1),
        "note": "the within-issuer homonym base rate among Form 3/4/5 filers: 1 of 721 8-K rows "
                "with an anchor has two owner CIKs sharing surname + given name at the issuer",
    },
    "reused_identifiers": {
        "pairs_whose_anchor_cik_carries_2plus_names": block(reused),
        "note": "8-K carries no identifier of its own; this is the Form 3/4/5 anchor side, i.e. "
                "research 17 F4's stratum seen from the 8-K",
    },
    "transitive_bridges": {
        "8k_only_blocks_with_3plus_full_keys": len(bridges["8k_only"]),
        "8k_plus_f4_blocks_with_3plus_full_keys": len(bridges["8k_plus_f4"]),
        "note": "a bridge needs a third key value between two others. None exists, for the same "
                "structural reason research 17 F5 gives: an exact-equality key makes 'shares a "
                "key with' an equivalence relation.",
    },
}

# ---- suffix veto: what it costs and buys on 8-K ----------------------------------------------
vetoed = [p for p in P if p["match"]["mi"] and p["suffix_veto"]]
summary["suffix_veto"] = {
    "pairs_matching_mi_but_vetoed": len(vetoed),
    "labels": dict(Counter(p["label"] for p in vetoed)),
    "examples": [{"a": p["key_fields"]["a_name"], "a_suffix": p["key_fields"]["a_suffix"],
                  "b": p["key_fields"]["b_name"], "b_suffix": p["key_fields"]["b_suffix"],
                  "label": p["label"]} for p in vetoed],
    "with_V_in_the_token_set": sum(1 for p in P if p["match"]["mi"] and c21.suffix_veto(
        p["key_fields"]["a_suffix"], p["key_fields"]["b_suffix"], c21.GEN_SUFFIXES_17)),
}

# ---- recall and review volume ------------------------------------------------------------------
# recall, on the labelled set: of pairs a Tier C comparator (surname + first initial) raises that
# are labelled `same`, the fraction the fixed key also matches.
same_fl = [p for p in P if p["match"]["fl"] and p["label"] == "same"]
summary["recall"] = {
    "labelled_same_pairs_raised_by_tier_c": len(same_fl),
    "of_which_the_fixed_key_matches": sum(1 for p in same_fl if p["key_fixed"]),
    "recall": round(sum(1 for p in same_fl if p["key_fixed"]) / len(same_fl), 5),
    "lost_to_the_middle_name_requirement": sum(1 for p in same_fl if not p["match"]["mi"]),
    "lost_to_the_suffix_veto": sum(1 for p in same_fl if p["match"]["mi"] and p["suffix_veto"]),
}

# review volume per 1,000 eligible 8-K records: raised by the Tier C comparator but not matched
# by the fixed key, so they fall to Steward review.
sh = k8.copy()
sh["gen"] = sh["suffix"].map(lambda s: "|".join(sorted(c21.gen_set(s))))
sh["kfixed"] = sh["k_mi"] + "#" + sh["gen"]
n_block = sh.groupby(["ctx", "block"])["rec_id"].transform("size")
n_key = sh.groupby(["ctx", "kfixed"])["rec_id"].transform("size")
n_mi = sh.groupby(["ctx", "k_mi"])["rec_id"].transform("size")
summary["review_volume"] = {
    "eligible_8k_records": int(len(sh)),
    "records_with_a_tier_c_candidate": int((n_block > 1).sum()),
    "records_with_a_fixed_key_candidate": int((n_key > 1).sum()),
    "records_to_review_fixed_key": int(((n_block > 1) & (n_key == 1)).sum()),
    "review_per_1000_fixed_key": round(1000 * ((n_block > 1) & (n_key == 1)).sum() / len(sh), 2),
    "review_per_1000_mi_without_veto": round(1000 * ((n_block > 1) & (n_mi == 1)).sum() / len(sh), 2),
    "auto_bind_decisions_fixed_key": int((n_key > 1).sum() - sh[n_key > 1].groupby(["ctx", "kfixed"]).ngroups),
}

# ---- pooled with research 17 -------------------------------------------------------------------
# research 17's 8-K pairs are a subset of this census and carry the same pair ids, so "pooling" is
# a re-label, not an addition. Reported explicitly so the two studies are not double counted.
r17_mi = [p for p in r17_8k if p["match"]["mi"]]
summary["pooled_with_research_17"] = {
    "r17_8k_pairs_at_mi": len(r17_mi),
    "r17_labels_at_mi": dict(Counter(p["label"] for p in r17_mi)),
    "all_r17_8k_pairs_are_in_this_census": all(p["pair_id"] in {q["pair_id"] for q in P} for p in r17_8k),
    "note": "research 21 relabelled research 17's own 281 8-K pairs with the same rules (verified "
            "identical at the draft stage) and then labelled 657 more from the same population. "
            "The pooled figure IS the census figure; nothing is added twice.",
    "r17_relabelled_deltas": [
        {"pair_id": p["pair_id"], "r17": q["label"], "r21": p["label"], "rule": p["labeler_rule"]}
        for p in P for q in [next((x for x in r17_8k if x["pair_id"] == p["pair_id"]), None)]
        if q and q["label"] != p["label"]],
}

# ---- sensitivity: what the result is WITHOUT research 21's own settling rules ----------------
# Ticket 20 Q2's objection was that the optimistic reading rested on unsettled pairs. Pass 2
# settles 37 of them at the fixed key. This block shows the result with pass 2 switched off, and
# with only its date-anchored settlements (L-21A/L-21B) accepted and its argued ones (L-21E,
# L-21C) rejected -- so a reader can see exactly how much of the conservative reading pass 2 buys.
d1 = Counter(p["draft_label"] for p in FIXED)
n1 = len(FIXED)
anchored_settle = sum(1 for p in FIXED if rule0(p) in ("L-21A", "L-21B"))
argued_settle = sum(1 for p in FIXED if rule0(p) in ("L-21E", "L-21C"))
summary["sensitivity_to_pass_2"] = {
    "pass2_settlements_at_the_fixed_key": {"date_anchored_L21A_L21B": anchored_settle,
                                           "argued_L21E_L21C": argued_settle,
                                           "left_unsettled_L21F": 1},
    "pass_1_only": {"n": n1, "labels": dict(d1),
                    "unknown_rules": dict(Counter(p["draft_rule"].split()[0] for p in FIXED
                                                  if p["draft_label"] == "unknown")),
                    "conservative": {"precision": round(d1["same"] / n1, 5),
                                     **wl(d1["same"], n1)},
                    "optimistic": {"precision": round((d1["same"] + d1["unknown"]) / n1, 5),
                                   **wl(d1["same"] + d1["unknown"], n1)},
                    "settled": {"n": d1["same"] + d1["different"],
                                "precision": 1.0 if not d1["different"] else None,
                                **wl(d1["same"], d1["same"] + d1["different"])}},
    "date_anchored_settlements_only": {"n": n1, "same": d1["same"] + anchored_settle,
                                       "precision": round((d1["same"] + anchored_settle) / n1, 5),
                                       **wl(d1["same"] + anchored_settle, n1),
                                       "note": "L-21E and L-21C settlements and the one L-21F "
                                               "unsettled pair all counted as errors"},
    "reading": "the conservative reading clears 99% at 97.5% only because of pass 2. The "
               "`settled` reading clears either way (pass 1 alone: LCB97.5 0.99387 on n = 623).",
}

# ---- clustering: the Wilson bound assumes independent trials ---------------------------------
summary["coverage"] = {
    "fixed_key_pairs": len(FIXED),
    "distinct_issuers": len({p["ctx"] for p in FIXED}),
    "distinct_8k_records": len({p["a"]["rec_id"] for p in FIXED}),
    "distinct_names_issuer_scoped": len({(p["ctx"], p["key_fields"]["a_name"].upper()) for p in FIXED}),
    "max_pairs_from_one_issuer": max(Counter(p["ctx"] for p in FIXED).values()),
    "note": "one pair per (issuer, 8-K name) in the X stratum and one per (issuer, fl key) group "
            "in K, so a pair is close to one distinct person; the Wilson bound still assumes "
            "independence it cannot fully have.",
}

summary["iapd"] = {"requests": 0,
                   "reason": "IAPD's individual endpoint is a strict lookup by CRD/OwnerID "
                             "(research 16 F2). 8-K Item 5.02 persons carry no CRD, so there is "
                             "no key to look them up by, and every label here was settled from "
                             "SEC-sourced data already on disk. `21-iapd-requests.jsonl` is "
                             "present and empty: zero requests, zero 403s, zero 429s."}

summary["inputs"] = {
    "records_parquet": {"path": str(c21.R17 / "records.parquet"),
                        "sha256": c17.sha256_file(c21.R17 / "records.parquet")},
    "21-pairs.jsonl": {"sha256": c17.sha256_file(c21.HERE / "21-pairs.jsonl")},
    "17-pairs.jsonl": {"sha256": c17.sha256_file(c21.HERE / "17-pairs.jsonl")},
    "sec_employment_event.parquet": {"sha256": c17.sha256_file(c17.EIGHTK)},
    "07-union-corpus.jsonl": {"sha256": c17.sha256_file(c17.F4_UNION)},
}

with open(c21.HERE / "21-summary.json", "w") as f:
    json.dump(summary, f, indent=1)
print(json.dumps({k: summary[k] for k in ("census", "fixed_key", "evidence_classes", "recall",
                                          "review_volume", "suffix_veto")}, indent=1)[:9000])
