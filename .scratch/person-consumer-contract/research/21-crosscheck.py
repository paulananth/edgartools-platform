"""Research 21, stage 4: two cross-checks the 8-K census cannot perform on itself.

**Why this stage exists.** Every `different` verdict the 8-K labeller can reach comes from a
middle-name or suffix *conflict* (rule `L-H1`), and the fixed key rejects those pairs anyway. So
the one error the key could actually make -- merging two genuinely different people who share
surname, given name and middle initial at one issuer -- is invisible to the 8-K labelling method
by construction. `unknown` is the strongest thing it can say (rule `L-21F`). The precision
measured on 8-K is therefore an upper bound on what that method can *detect*, not a blind one.

Two independent checks:

1. **The fixed key run against a source where identity is known.** Form 3/4/5 carries
   `owner_cik` on 100% of rows (research 17 F1), so on that source "two records, same issuer,
   different CIK" is a labelled `different` pair with no reading required. Research 17's homonym
   census (F3) enumerated all 11 such pairs. Here the *fixed* key -- `mi` plus the generational
   suffix veto -- is applied to them: how many would it auto-merge? That is a directly measured
   count of false merges, on 56,000+ decisions, with an identifier doing the labelling.

2. **The `V` token.** Research 17's suffix list carries `V` (fifth). `V` is also a common middle
   initial, and both name parsers strip suffix tokens out of the name core before building the
   key -- so any middle initial `V` is silently discarded and the `mi` key degrades to `fl` for
   that record. Ticket 20 Q3's list is `JR/SR/II/III/IV` only. This measures what the difference
   is worth.

Run: uv run --no-project --with pandas --with pyarrow python 21-crosscheck.py
"""
from __future__ import annotations

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
rec = rec[rec["shape"]]
f4p = rec[(rec["source"] == "f4") & (rec["event_type"] == "person")]
k8 = rec[rec["source"] == "8k"]
out = {}

# ---- 1. the fixed key against Form 3/4/5, where owner_cik labels every pair -------------------
lab = f4p[f4p["xref"] != ""]
rep = lab.sort_values(["filing", "rec_id"]).drop_duplicates(["ctx", "xref", "k_full"])
homonyms = []
for (ctx, kfl), g in rep.groupby(["ctx", "k_fl"]):
    ids = sorted(g["xref"].unique())
    if len(ids) < 2:
        continue
    for x, y in itertools.combinations(ids, 2):
        ga, gb = g[g["xref"] == x], g[g["xref"] == y]
        # would the fixed key merge ANY record of x with ANY record of y?
        merge = any(c21.fixed_key_match(ra.k_mi, rb.k_mi, ra.suffix, rb.suffix)
                    for ra in ga.itertuples() for rb in gb.itertuples())
        merge_mi_only = bool(set(ga["k_mi"]) & set(gb["k_mi"]))
        homonyms.append({"ctx": ctx, "a_cik": x, "b_cik": y,
                         "a_names": sorted(set(ga["raw_name"])), "b_names": sorted(set(gb["raw_name"])),
                         "issuer": ga["firm_name"].iloc[0],
                         "fixed_key_merges": merge, "mi_merges": merge_mi_only})
merged = [h for h in homonyms if h["fixed_key_merges"]]
# total auto-bind decisions the fixed key makes on Form 3/4/5, for the denominator
sh = f4p.copy()
sh["gen"] = sh["suffix"].map(lambda s: "|".join(sorted(c21.gen_set(s))))
sh["kfixed"] = sh["k_mi"] + "#" + sh["gen"]
grp = sh.groupby(["ctx", "kfixed"])["rec_id"].size()
decisions = int(grp[grp > 1].sum() - (grp > 1).sum())
out["form345_identifier_labelled"] = {
    "same_issuer_same_surname_and_given_name_cik_pairs": len(homonyms),
    "all_known_different_by_owner_cik": True,
    "would_be_merged_by_mi_alone": sum(1 for h in homonyms if h["mi_merges"]),
    "would_be_merged_by_the_fixed_key": len(merged),
    "prevented_by_the_suffix_veto": sum(1 for h in homonyms if h["mi_merges"] and not h["fixed_key_merges"]),
    "fixed_key_auto_bind_decisions_on_form345": decisions,
    "false_merge_rate_per_decision": round(len(merged) / decisions, 9) if decisions else None,
    "false_merge_rate_per_10000_decisions": round(1e4 * len(merged) / decisions, 4) if decisions else None,
    "merged_pairs": merged,
    "all_pairs": homonyms,
}

# ---- 2. the `V` token ---------------------------------------------------------------------------
def has_v(s):
    return "V" in (s or "").split(" ")


v8 = k8[k8["suffix"].map(has_v)]
vf = f4p[f4p["suffix"].map(has_v)]
out["v_token"] = {
    "8k_records_whose_parsed_suffix_holds_V": int(len(v8)),
    "f4_records_whose_parsed_suffix_holds_V": int(len(vf)),
    "8k_of_those_with_an_otherwise_empty_middle": int((v8["middle"] == "").sum()),
    "f4_of_those_with_an_otherwise_empty_middle": int((vf["middle"] == "").sum()),
    "examples_8k": sorted(set(v8["raw_name"]))[:10],
    "examples_f4": sorted(set(vf["raw_name"]))[:10],
    "note": "a record whose parsed suffix holds V and whose middle is otherwise empty has had its "
            "middle initial discarded: its `mi` key equals its `fl` key, so the key is one "
            "variant looser than ticket 20 specifies for exactly those names.",
}

with open(c21.HERE / "21-crosscheck.json", "w") as f:
    json.dump(out, f, indent=1, default=str)
print(json.dumps(out, indent=1, default=str)[:6000])
