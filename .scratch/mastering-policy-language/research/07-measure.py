#!/usr/bin/env python3
"""THROWAWAY — Mastering Policy Language research 07, part 1.

Measures the "one `owner_cik` -> at most one Person" claim in both directions over the
research 18 primary corpus (18-owners.jsonl), the legacy corpus (bronze filings/sec/ primaries
parsed by 18-classify.py's `parse` stage, joined here to bronze submissions.json the same way
`stage_parse` does), and their union.

  uv run --no-project python 07-measure.py \
      --primary ../../person-consumer-contract/research/18-owners.jsonl \
      --legacy  <scratchpad>/r18/legacy_rows.jsonl \
      --submissions <scratchpad>/r18/submissions \
      --out-json 07-cardinality.json --out-dir <scratchpad>/r07

Imports `norm_name`, `rule_combo_j`, `load_submission`, `_PERSON_SUFFIX`, `entity_tokens`
from 18-classify.py (which blocks sockets at import). Nothing here opens a socket.

Forward  = per owner_cik, distinct normalized names (the rule's own claim; a violation is a
           CIK carrying two genuinely different people).
Reverse  = per normalized name (and per (issuer_cik, name)), distinct owner_ciks (not a
           violation of the claim; it is the Identity Consolidation load: one person with two
           SEC accounts vs. two people sharing a name).

The automatic "name relationship" classes below are a pre-sort for inspection, not the
finding; the labelled sample is the finding and is the researcher's own reading.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import random
import sys
from collections import Counter, defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "person-consumer-contract", "research"))
import importlib  # noqa: E402

c18 = importlib.import_module("18-classify")  # noqa: E402  (module name has a dash)
norm_name, rule_combo_j, load_submission = c18.norm_name, c18.rule_combo_j, c18.load_submission
PERSON_SUFFIX, entity_tokens, flag_combo = c18._PERSON_SUFFIX, c18.entity_tokens, c18.flag_combo

SEED = 20260920
Z = 1.959964  # two-sided 95% == one-sided 97.5%, the coverage policy-person.json bars declare


def wilson(k: int, n: int, z: float = Z) -> tuple[float, float, float]:
    if n == 0:
        return (float("nan"), float("nan"), float("nan"))
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (p, c - h, c + h)


def per10k(k: int, n: int) -> dict:
    p, lo, hi = wilson(k, n)
    return {"k": k, "n": n, "rate_per_10k": round(p * 1e4, 3) if n else None,
            "wilson95_per_10k": [round(lo * 1e4, 3), round(hi * 1e4, 3)] if n else None}


# ----------------------------------------------------------------------------------------
# Name relationship pre-sort (automatic). Order-insensitive because rptOwnerName is what the
# filer typed: mostly EDGAR-conformed "LAST FIRST MIDDLE" but not always.
# ----------------------------------------------------------------------------------------

NICKNAMES = {
    "BOB": "ROBERT", "ROB": "ROBERT", "BOBBY": "ROBERT", "BILL": "WILLIAM", "WILL": "WILLIAM",
    "BILLY": "WILLIAM", "JIM": "JAMES", "JIMMY": "JAMES", "MIKE": "MICHAEL", "DICK": "RICHARD",
    "RICK": "RICHARD", "RICH": "RICHARD", "TOM": "THOMAS", "TOMMY": "THOMAS", "DAVE": "DAVID",
    "DAN": "DANIEL", "DANNY": "DANIEL", "STEVE": "STEVEN", "STEPHEN": "STEVEN", "ED": "EDWARD",
    "TED": "EDWARD", "EDDIE": "EDWARD", "CHRIS": "CHRISTOPHER", "CHUCK": "CHARLES",
    "CHARLIE": "CHARLES", "JOE": "JOSEPH", "JOEY": "JOSEPH", "TONY": "ANTHONY", "ANDY": "ANDREW",
    "DREW": "ANDREW", "MATT": "MATTHEW", "PAT": "PATRICK", "PATTY": "PATRICIA", "PEGGY": "MARGARET",
    "MEG": "MARGARET", "BETH": "ELIZABETH", "LIZ": "ELIZABETH", "BETTY": "ELIZABETH", "SUE": "SUSAN",
    "KATE": "KATHERINE", "KATHY": "KATHERINE", "KATIE": "KATHERINE", "CATHY": "CATHERINE",
    "JEN": "JENNIFER", "JENNY": "JENNIFER", "JACK": "JOHN", "JOHNNY": "JOHN", "JON": "JONATHAN",
    "NICK": "NICHOLAS", "GREG": "GREGORY", "JEFF": "JEFFREY", "GEOFF": "GEOFFREY", "KEN": "KENNETH",
    "KENNY": "KENNETH", "LARRY": "LAWRENCE", "TIM": "TIMOTHY", "SAM": "SAMUEL", "BEN": "BENJAMIN",
    "ALEX": "ALEXANDER", "FRED": "FREDERICK", "HANK": "HENRY", "HARRY": "HENRY", "RON": "RONALD",
    "RONNIE": "RONALD", "DON": "DONALD", "DONNIE": "DONALD", "RAY": "RAYMOND", "PHIL": "PHILIP",
    "PHILLIP": "PHILIP", "LEN": "LEONARD", "LEO": "LEONARD", "GENE": "EUGENE", "ART": "ARTHUR",
    "BRAD": "BRADLEY", "DOUG": "DOUGLAS", "GABE": "GABRIEL", "HERB": "HERBERT", "JERRY": "GERALD",
    "TERRY": "TERENCE", "VINCE": "VINCENT", "WALT": "WALTER", "ZACH": "ZACHARY", "ABE": "ABRAHAM",
    "MAX": "MAXIMILIAN", "NATE": "NATHAN", "NATHANIEL": "NATHAN", "STAN": "STANLEY",
    "JOSH": "JOSHUA", "MARTY": "MARTIN", "NORM": "NORMAN", "RANDY": "RANDALL", "RUSS": "RUSSELL",
    "SANDY": "SANDRA", "DEBBIE": "DEBORAH", "DEB": "DEBORAH", "BARB": "BARBARA", "TRISH": "PATRICIA",
    "CINDY": "CYNTHIA", "MANDY": "AMANDA", "BECKY": "REBECCA", "VICKI": "VICTORIA", "TINA": "CHRISTINA",
    "CHRISTINE": "CHRISTINA", "MOLLY": "MARY", "POLLY": "MARY", "JAKE": "JACOB", "JOSE": "JOSEPH",
    "GUS": "AUGUSTUS", "LOU": "LOUIS", "LEW": "LEWIS", "AL": "ALBERT", "BERT": "ALBERT",
    "BERNIE": "BERNARD", "CAL": "CALVIN", "CLIFF": "CLIFFORD", "DUKE": "MARMADUKE", "ELI": "ELIJAH",
    "FRANK": "FRANCIS", "FRANKIE": "FRANCIS", "HAL": "HAROLD", "HOWIE": "HOWARD", "IKE": "ISAAC",
    "JEB": "JEBEDIAH", "JOEL": "JOEL", "MANNY": "MANUEL", "MEL": "MELVIN", "MITCH": "MITCHELL",
    "MORT": "MORTIMER", "NED": "EDWARD", "OLLIE": "OLIVER", "OZZIE": "OSWALD", "PETE": "PETER",
    "RALPH": "RAPHAEL", "REG": "REGINALD", "ROD": "RODNEY", "ROGER": "ROGER", "SID": "SIDNEY",
    "SOL": "SOLOMON", "SY": "SEYMOUR", "TEDDY": "THEODORE", "THEO": "THEODORE", "VIC": "VICTOR",
    "WES": "WESLEY", "WOODY": "WOODROW",
}


def canon_tokens(name: str) -> tuple[list[str], list[str], list[str]]:
    """(full tokens, initials, suffixes) of a normalized name; nicknames mapped to formal form."""
    toks = [t for t in norm_name(name).split() if t]
    suf = [t for t in toks if t in PERSON_SUFFIX]
    rest = [t for t in toks if t not in PERSON_SUFFIX]
    full = [NICKNAMES.get(t, t) for t in rest if len(t) > 1]
    init = [t for t in rest if len(t) == 1]
    return full, init, suf


def initials_compatible(init: list[str], full_other: list[str]) -> bool:
    firsts = {t[0] for t in full_other}
    return all(i in firsts for i in init)


def name_relation(a: str, b: str) -> str:
    """Automatic pre-sort of two names found under one owner_cik (or one person)."""
    if norm_name(a) == norm_name(b):
        return "identical"
    ea, eb = entity_tokens(a), entity_tokens(b)
    if bool(ea) != bool(eb):
        return "entity_vs_person_name"
    fa, ia, sa = canon_tokens(a)
    fb, ib, sb = canon_tokens(b)
    A, B = set(fa), set(fb)
    shared = A & B
    if set(sa) != set(sb) and shared and (A <= B or B <= A or len(shared) >= 2):
        return "suffix_differs"           # JR vs SR / II vs III with the same tokens: father/son?
    if (A <= B and initials_compatible(ia, fb)) or (B <= A and initials_compatible(ib, fa)):
        return "variant_subset"           # middle name added/dropped, initial expanded, nickname
    if len(shared) >= 2:
        return "variant_reorder_or_middle"  # same two anchors, one differing token (middle name / typo)
    if len(shared) == 1:
        # one anchor shared: surname kept and given name differs (different person, or nickname
        # not in the map), or given name kept and surname differs (marriage / legal change)
        t = next(iter(shared))
        pos_a = fa.index(t) if t in fa else -1
        pos_b = fb.index(t) if t in fb else -1
        if pos_a == 0 and pos_b == 0:
            return "one_shared_first_token"     # conformed order: surname shared, given differs
        return "one_shared_other_token"         # given name shared, surname differs, or reordered
    # zero shared full tokens: prefix / typo tolerance (e.g. "MICHEAL"/"MICHAEL", "CHRIS"/"CHRISTOPHER")
    def near(x: str, y: str) -> bool:
        return (len(x) >= 4 and len(y) >= 4 and (x.startswith(y[:4]) or y.startswith(x[:4]))) or (
            len(x) >= 4 and len(y) >= 4 and sum(1 for p, q in zip(x, y) if p != q) + abs(len(x) - len(y)) <= 2)
    nears = sum(1 for x in A for y in B if near(x, y))
    if nears >= 2 or (nears >= 1 and (initials_compatible(ia, fb) or initials_compatible(ib, fa)) and (ia or ib)):
        return "typo_or_prefix"
    if nears == 1:
        return "one_near_token"
    return "no_overlap"


CLASS_ORDER = ["identical", "variant_subset", "variant_reorder_or_middle", "typo_or_prefix", "suffix_differs",
               "one_shared_other_token", "one_shared_first_token", "one_near_token",
               "entity_vs_person_name", "no_overlap"]
SEVERITY = {c: i for i, c in enumerate(CLASS_ORDER)}


def group_relation(names: list[str]) -> str:
    """Worst pairwise relation against the most frequent name (names ordered by frequency)."""
    head = names[0]
    worst = "identical"
    for other in names[1:]:
        rel = name_relation(head, other)
        if SEVERITY[rel] > SEVERITY[worst]:
            worst = rel
    return worst


# ----------------------------------------------------------------------------------------
# Loading
# ----------------------------------------------------------------------------------------

def load_rows(path: str, corpus: str) -> list[dict]:
    rows = []
    with open(path) as f:
        for line in f:
            r = json.loads(line)
            r["corpus"] = corpus
            rows.append(r)
    return rows


def join_submissions(rows: list[dict], sub_dir: str) -> dict:
    """The join `stage_parse` (18-classify.py:356-369) does; legacy rows lack it."""
    cache: dict = {}
    n_present = n_absent = 0
    for r in rows:
        if "sub_present" in r:
            continue
        r["flag_combo"] = r.get("flag_combo") or flag_combo(r)
        cik = r["owner_cik"]
        if cik is None:
            r["sub_present"] = False
            n_absent += 1
            continue
        if cik not in cache:
            cache[cik] = load_submission(sub_dir, cik)
        s = cache[cik]
        if s is None:
            r["sub_present"] = False
            n_absent += 1
        else:
            r.update(s)
            n_present += 1
    return {"joined_rows": n_present, "rows_without_submissions": n_absent,
            "ciks_looked_up": len(cache), "ciks_with_submissions": sum(1 for v in cache.values() if v)}


def dedupe_union(primary: list[dict], legacy: list[dict]) -> tuple[list[dict], dict]:
    seen = set()
    out = []
    dup = 0
    for r in legacy + primary:  # legacy first: the older bronze path
        k = (r["accession"], r["owner_index"])
        if k in seen:
            dup += 1
            continue
        seen.add(k)
        out.append(r)
    return out, {"rows": len(out), "duplicate_accession_owner_index_dropped": dup}


# ----------------------------------------------------------------------------------------
# Measurement
# ----------------------------------------------------------------------------------------

def measure(rows: list[dict], label: str, rng: random.Random, sample_out: dict, restrict_person: bool) -> dict:
    """Forward and reverse cardinality over `rows` (optionally only C-J person rows)."""
    if restrict_person:
        rows = [r for r in rows if r["cj"] == "person"]
    rows = [r for r in rows if r["owner_cik"] is not None]
    n_rows = len(rows)

    # forward: cik -> Counter(norm_name)
    fwd: dict[int, Counter] = defaultdict(Counter)
    fwd_raw: dict[int, dict] = defaultdict(dict)
    issuers: dict[int, set] = defaultdict(set)
    for r in rows:
        nn = norm_name(r["owner_name"])
        fwd[r["owner_cik"]][nn] += 1
        fwd_raw[r["owner_cik"]].setdefault(nn, r["owner_name"])
        issuers[r["owner_cik"]].add(r["issuer_cik"])
    dist = Counter(len(c) for c in fwd.values())
    multi = {cik: c for cik, c in fwd.items() if len(c) > 1}
    classes = Counter()
    per_cik_class = {}
    rows_under_multi = 0
    rows_minority = 0  # rows carrying a name other than the CIK's most frequent one
    for cik, c in multi.items():
        names = [n for n, _ in c.most_common()]
        rel = group_relation(names)
        classes[rel] += 1
        per_cik_class[cik] = rel
        rows_under_multi += sum(c.values())
        rows_minority += sum(c.values()) - c.most_common(1)[0][1]
    # rows whose name is in a "candidate genuinely different person" class
    candidate_classes = {"no_overlap", "entity_vs_person_name", "one_near_token", "one_shared_first_token"}
    cand_ciks = [cik for cik, rel in per_cik_class.items() if rel in candidate_classes]
    cand_rows_minority = sum(sum(fwd[cik].values()) - fwd[cik].most_common(1)[0][1] for cik in cand_ciks)

    # inspection sample: every candidate CIK, plus up to 40 of each other multi-name class
    inspect = []
    by_class = defaultdict(list)
    for cik, rel in per_cik_class.items():
        by_class[rel].append(cik)
    for rel, ciks in sorted(by_class.items()):
        take = sorted(ciks) if (rel in candidate_classes or len(ciks) <= 40) else sorted(rng.sample(ciks, 40))
        for cik in take:
            inspect.append({
                "corpus": label, "owner_cik": cik, "auto_class": rel,
                "names": [{"norm": n, "raw": fwd_raw[cik][n], "rows": k} for n, k in fwd[cik].most_common()],
                "issuers": sorted(x for x in issuers[cik] if x is not None),
                "sub_name": next((r.get("sub_name") for r in rows if r["owner_cik"] == cik and r.get("sub_name")), None),
                "label": None, "label_reason": None,
            })
    sample_out[f"forward|{label}|{'person' if restrict_person else 'all'}"] = inspect

    # reverse: name -> set(cik); (issuer, name) -> set(cik)
    rev: dict[str, set] = defaultdict(set)
    rev_issuer: dict[tuple, set] = defaultdict(set)
    name_rows: Counter = Counter()
    for r in rows:
        nn = norm_name(r["owner_name"])
        rev[nn].add(r["owner_cik"])
        rev_issuer[(r["issuer_cik"], nn)].add(r["owner_cik"])
        name_rows[nn] += 1
    rdist = Counter(len(s) for s in rev.values())
    ridist = Counter(len(s) for s in rev_issuer.values())
    multi_name = {n: s for n, s in rev.items() if len(s) > 1}
    multi_issuer_name = {k: s for k, s in rev_issuer.items() if len(s) > 1}
    rev_rows = sum(name_rows[n] for n in multi_name)
    rev_issuer_rows = sum(1 for r in rows if (r["issuer_cik"], norm_name(r["owner_name"])) in multi_issuer_name)

    # reverse inspection: every (issuer, name) with >1 CIK; a sample of name-only collisions
    rinspect = []
    sub_by_cik = {}
    for r in rows:
        if r.get("sub_present") and r["owner_cik"] not in sub_by_cik:
            sub_by_cik[r["owner_cik"]] = {"sub_name": r.get("sub_name"), "business_state": r.get("business_state"),
                                         "mailing_street": r.get("mailing_street"), "n_recent_filings": r.get("n_recent_filings"),
                                         "forms_top": r.get("forms_top")}
    for (iss, nn), ciks in sorted(multi_issuer_name.items(), key=lambda kv: (str(kv[0][0]), kv[0][1])):
        rinspect.append({"corpus": label, "kind": "issuer+name", "issuer_cik": iss, "norm_name": nn,
                         "ciks": [{"cik": c, "rows": sum(1 for r in rows if r["owner_cik"] == c and norm_name(r["owner_name"]) == nn),
                                   "all_names_on_cik": [n for n, _ in fwd[c].most_common()],
                                   "submissions": sub_by_cik.get(c)} for c in sorted(ciks)],
                         "label": None, "label_reason": None})
    name_only = sorted(n for n in multi_name if not any(n == k[1] for k in multi_issuer_name))
    for nn in (name_only if len(name_only) <= 60 else sorted(rng.sample(name_only, 60))):
        rinspect.append({"corpus": label, "kind": "name-only", "norm_name": nn,
                         "ciks": [{"cik": c, "issuers": sorted(x for x in issuers[c] if x is not None),
                                   "all_names_on_cik": [n for n, _ in fwd[c].most_common()],
                                   "submissions": sub_by_cik.get(c)} for c in sorted(multi_name[nn])],
                         "label": None, "label_reason": None})
    sample_out[f"reverse|{label}|{'person' if restrict_person else 'all'}"] = rinspect

    return {
        "rows": n_rows,
        "distinct_owner_ciks": len(fwd),
        "forward": {
            "names_per_cik_distribution": {str(k): v for k, v in sorted(dist.items())},
            "ciks_with_multiple_names": len(multi),
            "rows_under_multi_name_ciks": rows_under_multi,
            "rows_carrying_a_non_majority_name": rows_minority,
            "auto_class_of_multi_name_ciks": dict(classes.most_common()),
            "candidate_different_person_ciks": len(cand_ciks),
            "candidate_different_person_rows_non_majority": cand_rows_minority,
            "rate_any_second_name_per_10k_ciks": per10k(len(multi), len(fwd)),
            "rate_any_second_name_per_10k_rows": per10k(rows_minority, n_rows),
            "rate_candidate_violation_per_10k_ciks_UNLABELLED": per10k(len(cand_ciks), len(fwd)),
            "rate_candidate_violation_per_10k_rows_UNLABELLED": per10k(cand_rows_minority, n_rows),
        },
        "reverse": {
            "ciks_per_name_distribution": {str(k): v for k, v in sorted(rdist.items())},
            "ciks_per_issuer_name_distribution": {str(k): v for k, v in sorted(ridist.items())},
            "distinct_names": len(rev),
            "names_with_multiple_ciks": len(multi_name),
            "rows_under_multi_cik_names": rev_rows,
            "issuer_name_pairs": len(rev_issuer),
            "issuer_name_pairs_with_multiple_ciks": len(multi_issuer_name),
            "rows_under_multi_cik_issuer_name_pairs": rev_issuer_rows,
            "rate_name_collision_per_10k_names": per10k(len(multi_name), len(rev)),
            "rate_issuer_name_collision_per_10k_pairs": per10k(len(multi_issuer_name), len(rev_issuer)),
            "rate_issuer_name_collision_per_10k_rows": per10k(rev_issuer_rows, n_rows),
        },
    }


def sha(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--primary", required=True)
    ap.add_argument("--legacy", required=True)
    ap.add_argument("--submissions", required=True)
    ap.add_argument("--out-json", required=True)
    ap.add_argument("--out-dir", required=True, help="scratchpad dir for the inspection samples and the union corpus")
    args = ap.parse_args()
    os.makedirs(args.out_dir, exist_ok=True)
    rng = random.Random(SEED)

    primary = load_rows(args.primary, "primary")
    legacy = load_rows(args.legacy, "legacy")
    join_stats = join_submissions(legacy, args.submissions)
    for r in primary + legacy:
        r["cj"] = rule_combo_j(r)
    union, union_stats = dedupe_union(primary, legacy)

    out = {
        "_throwaway": "research 07 measurement; inputs and their SHA-256 below",
        "inputs": {"primary": {"path": args.primary, "sha256": sha(args.primary), "rows": len(primary)},
                   "legacy": {"path": args.legacy, "sha256": sha(args.legacy), "rows": len(legacy)},
                   "legacy_submissions_join": join_stats, "union": union_stats},
        "cj_verdicts": {c: dict(Counter(r["cj"] for r in rs)) for c, rs in (("primary", primary), ("legacy", legacy), ("union", union))},
        "corpora": {},
    }
    samples: dict = {}
    for label, rows in (("primary", primary), ("legacy", legacy), ("union", union)):
        out["corpora"][label] = {"all_rows": measure(rows, label, rng, samples, restrict_person=False),
                                 "cj_person_rows": measure(rows, label, rng, samples, restrict_person=True)}
        print(label, json.dumps({k: out["corpora"][label][k]["forward"]["ciks_with_multiple_names"] for k in out["corpora"][label]}), file=sys.stderr)

    with open(os.path.join(args.out_dir, "07-inspection-samples.json"), "w") as f:
        json.dump(samples, f, indent=1, ensure_ascii=False)
    # the union corpus, C-J verdict attached, in (accession, owner_index) order -- the binding run's input
    union_sorted = sorted(union, key=lambda r: (r["accession"], r["owner_index"]))
    keep = ("corpus", "accession", "owner_index", "form", "period", "issuer_cik", "issuer_name", "owner_cik",
            "owner_name", "flag_combo", "cj", "sub_present", "sub_name", "entity_type", "business_state", "mailing_street")
    with open(os.path.join(args.out_dir, "07-union-corpus.jsonl"), "w") as f:
        for r in union_sorted:
            f.write(json.dumps({k: r.get(k) for k in keep}, ensure_ascii=False) + "\n")
    out["union_corpus_file"] = {"path": os.path.join(args.out_dir, "07-union-corpus.jsonl"),
                                "sha256": sha(os.path.join(args.out_dir, "07-union-corpus.jsonl")),
                                "order": "(accession, owner_index), the key stage_sample uses (18-classify.py:435)"}
    with open(args.out_json, "w") as f:
        json.dump(out, f, indent=1, ensure_ascii=False)
    print("wrote", args.out_json, file=sys.stderr)


if __name__ == "__main__":
    main()
