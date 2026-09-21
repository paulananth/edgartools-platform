"""Research 21, stage 2: label the 8-K census.

Three passes, in this order:

1. **Research 17's own K/X rules, copied verbatim** (`17-label.py:35-145, 227-302`). They are
   reproduced here rather than imported because `17-label.py` writes files at import time. The
   copy is verified, not asserted: `--verify` re-labels the 281 pairs research 17 already
   labelled and fails if any draft label differs from research 17's `draft_label`.

2. **Research 21's own settling rules** (`L-21A` .. `L-21F`), applied only to pairs pass 1 left
   `unknown`. Each is stated once, here, and applied to the whole census -- none is hand-fitted
   to a pair. They exist because three of research 17's `unknown` verdicts rest on premises that
   the data does not support (see the findings, "Settling research 17's eight unsettled pairs").

3. **`21-overrides.json`**, my own per-pair reading, one line each with its reason.

**Labels never read the key.** No rule in any pass asks whether `k_mi` matches; they read the
Form 3/4/5 filer CIK at the issuer, the form type (3 vs 4), the filing periods, the 8-K event
sequence, and the middle-name / generational-suffix *conflict* that the key's looser variants
ignore. `unknown` is reported, never folded into `same`. A fourth label, `ineligible`, marks a
row that is not a person name at all and therefore never reaches any tier; it is excluded from
the eligible denominator and counted as an error in the conservative reading.

Run: uv run --no-project --with pandas python 21-label.py [--verify]
"""
from __future__ import annotations

import importlib.util
import json
import re
import sys
from collections import Counter
from datetime import date
from pathlib import Path

_spec = importlib.util.spec_from_file_location("c21", Path(__file__).with_name("21-common.py"))
c21 = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(c21)
c17 = c21.c17

pairs = [json.loads(l) for l in open(c21.R21 / "pairs_draft.jsonl")]
overrides = {}
_p = Path(__file__).with_name("21-overrides.json")
if _p.exists():
    overrides = json.load(open(_p))

# ============================ pass 1: research 17's rules, verbatim =============================
# --- 17-label.py:45-90, unchanged ---------------------------------------------------------------


def edit1(a: str, b: str) -> bool:
    if abs(len(a) - len(b)) > 1:
        return False
    if len(a) == len(b):
        return sum(x != y for x, y in zip(a, b)) <= 1
    s, l = (a, b) if len(a) < len(b) else (b, a)
    for i in range(len(l)):
        if l[:i] + l[i + 1:] == s:
            return True
    return False


def mids(side) -> list[str]:
    return [t for t in side["k_nosuffix"].split("|")[2].split(" ") if t]


def sfx(side) -> str:
    return side["k_full"].split("|")[3]


GEN = ("JR", "SR", "II", "III", "IV", "V")


def middle_relation(a, b) -> str:
    ma, mb = mids(a), mids(b)
    if ma == mb:
        return "equal"
    if not ma or not mb:
        return "absent"
    x, y = ma[0], mb[0]
    if (len(x) == 1 and y.startswith(x)) or (len(y) == 1 and x.startswith(y)):
        return "initial-of"
    if len(x) >= 3 and len(y) >= 3 and edit1(x, y):
        return "typo"
    return "conflict"


def suffix_relation(a, b) -> str:
    sa, sb = {t for t in sfx(a).split(" ") if t in GEN}, {t for t in sfx(b).split(" ") if t in GEN}
    if sa == sb:
        return "equal"
    if not sa or not sb:
        return "absent"
    return "conflict"


# --- 17-label.py:227-302 (the K and X branches), unchanged --------------------------------------


def draft_17(p: dict) -> tuple[str, str, str]:
    a, b = p["a"], p["b"]
    st = p["stratum"]
    if st == "K":
        anc = p.get("anchor") or {}
        ciks = anc.get("f4_ciks_with_fl") or []
        ev = f"events {p.get('group_events')}; anchor ciks={ciks}"
        mr = middle_relation(a, b)
        if mr == "conflict":
            return "different", ev + "; conflicting middle names", "L-H1 conflicting middle names"
        if len(ciks) == 1:
            return "same", ev + f"; one Form 3/4/5 CIK {ciks[0]} carries this name at the issuer; flags {anc.get('f4_flags')}", \
                "L-K1 single Form 3/4/5 CIK at the issuer anchors both events"
        if len(ciks) > 1:
            return "unknown", ev + "; two CIKs carry this name at the issuer", "L-K3 homonym at issuer (two CIKs)"
        ra, rb = c17.role_class_text(a["title"], default="UNK"), c17.role_class_text(b["title"], default="UNK")
        evs = p.get("group_events") or []
        types = [e[1] for e in evs]
        if ra != "UNK" and rb != "UNK" and ra != rb:
            if len({e[0] for e in evs}) >= 2 and all(t == "appointment" for t in types):
                return "same", ev + f"; two appointments of one name in different role classes ({ra} then {rb}): officer seated on the board or director made officer (continuity, no anchor)", \
                    "L-K7 no anchor; officer/director role change (promotion or board seat)"
            return "unknown", ev + "; role classes differ, no anchor", "L-K4 no anchor, role classes differ"
        if len({e[0] for e in evs}) >= 2 and types and types[0] == "appointment" and "departure" in types[1:]:
            return "same", ev + "; appointment then departure of the same role at the same issuer (timeline continuity, no anchor)", \
                "L-K5 no anchor; appointment-then-departure continuity"
        if len({e[0] for e in evs}) >= 2 and all(t == "appointment" for t in types):
            return "same", ev + "; repeated appointment/re-election events of the same role (timeline continuity, no anchor)", \
                "L-K6 no anchor; repeated appointments of the same role"
        if len({e[0] for e in evs}) >= 2 and types and all(t in ("departure", "appointment") for t in types):
            return "same", ev + "; repeated departure events, or departure then re-appointment, of one name at one issuer (continuity, no anchor)", \
                "L-K8 no anchor; repeated departure or departure-then-reappointment"
        return "unknown", ev + "; no anchor; sequence not coherent", "L-K2 no anchor; sequence not coherent"
    if st == "X":
        f4d = p.get("f4_periods") or []
        ev = f"src events {p.get('src_events')}; F4 cik {b['xref']} flags {p.get('f4_flags')} titles {p.get('f4_titles')} periods {f4d}"
        mr = middle_relation(a, b)
        if mr == "conflict":
            return "different", ev + "; conflicting middle names", "L-H1 conflicting middle names"
        if len(p.get("f4_ciks_with_fl") or []) > 1:
            return "unknown", ev + "; two CIKs carry this name at the issuer", "L-X4 homonym at issuer (two CIKs)"
        src_roles = {c17.role_class_text(t, default="UNK") for _, _, t in (p.get("src_events") or [])} - {"UNK"}
        f4_roles = set()
        for fc in p.get("f4_flags") or []:
            f4_roles |= c17.role_set_flags(fc)
        role_ok = (not src_roles) or bool(src_roles & f4_roles)
        date_ok = None
        try:
            d0 = date.fromisoformat(f4d[0][:10]) if f4d else None
            for dt_, et, _ in (p.get("src_events") or []):
                if et == "appointment" and dt_ and d0:
                    dd = abs((date.fromisoformat(dt_[:10]) - d0).days)
                    date_ok = dd <= 45 or date_ok
        except Exception:
            pass
        if role_ok and date_ok:
            return "same", ev + "; role agrees and appointment date within 45 days of first Form 3/4 period", "L-X1 role + date anchor"
        contra = False
        try:
            d0 = date.fromisoformat(f4d[0][:10]) if f4d else None
            d1 = date.fromisoformat(f4d[1][:10]) if f4d else None
            for dt_, et, _ in (p.get("src_events") or []):
                d = date.fromisoformat(dt_[:10])
                if et == "appointment" and d1 and (d - d1).days > 400:
                    contra = True
                if et == "departure" and d0 and (d0 - d).days > 400:
                    contra = True
        except Exception:
            pass
        if role_ok and not contra:
            return "same", ev + "; role agrees, Form 3/4/5 filing window compatible with the event timeline", \
                "L-X2 role agreement, timeline compatible (no date anchor)"
        if role_ok:
            return "unknown", ev + "; role agrees but Form 3/4/5 window contradicts the event timeline", "L-X3 timeline contradiction"
        return "unknown", ev + "; role disagreement", "L-X5 role disagreement"
    return "unknown", "no rule", "none"


# ============================ pass 2: research 21's settling rules ==============================
#
# L-21A  Form 3 anchor. X pair; exactly one Form 3/4/5 CIK carries the name at the issuer; that
#        CIK's earliest row at the issuer is a **Form 3** -- the initial statement of beneficial
#        ownership, so the insider relationship demonstrably began then -- and an 8-K appointment
#        falls within 45 days of it => same. Role is not consulted: ticket 20 Q3 makes role
#        evidence, never key.
# L-21B  Co-presence. X pair; exactly one CIK; an 8-K event date falls **inside** that CIK's
#        Form 3/4/5 activity window at the issuer, so the named person was a reporting insider of
#        that issuer on that date => same.
# L-21C  A Form 4 does not date the relationship. Research 17's L-X3 treats the earliest Form
#        3/4/5 period in the corpus as the start of the insider relationship. That premise holds
#        only when the earliest row is a Form 3. A **Form 4** is a change report that presupposes
#        a Form 3 already on file, and this corpus is a recent slice (research 17 Limits), so an
#        8-K event long before the first Form 4 is a gap in the corpus, not a contradiction.
#        Where L-X3 fired and the earliest row is a Form 4 => the contradiction is withdrawn and
#        the pair falls through to L-X2's test.
# L-21E  Role disagreement is not evidence of a different person. Research 17 F6 measured the
#        role element on this exact source: of 8-K pairs with inconsistent roles, 32 are the same
#        person and **0** are different. Ticket 20 Q3 adopts that ("role and flags are evidence,
#        never key"). Where L-X5 or L-K4 fired on role disagreement alone, with exactly one
#        anchoring CIK (L-X5) or a coherent event sequence (L-K4) and no name conflict => same.
# L-21F  Not settled, stated as such. Where the only evidence that would separate two candidates
#        is the middle initial itself, settling the pair would re-apply the key and prove nothing
#        (see the method note above). Such pairs stay `unknown` and are named in the findings.
#
# L-21D is deliberately absent: an earlier draft used the DEF 14A proxy to separate two homonyms
# by middle name, which is the same circularity L-21F refuses.

GEN_RE = re.compile(r"\b(JR|SR|II|III|IV)\b")


def settle_21(p: dict, lab: str, ev: str, rule: str) -> tuple[str, str, str]:
    if lab != "unknown":
        return lab, ev, rule
    a, b = p["a"], p["b"]
    if p["stratum"] == "X":
        one_cik = len(p.get("f4_ciks_with_fl") or []) == 1
        w = p.get("f4_all_periods_this_cik") or []
        forms = p.get("f4_forms_this_cik") or []
        earliest_form = forms[0] if forms else ""
        ev_dates = [(d, t) for d, t, _ in (p.get("src_events") or []) if d]
        if one_cik and w and w[0] and w[0] != "None":
            try:
                d0, d1 = date.fromisoformat(w[0][:10]), date.fromisoformat(w[1][:10])
            except Exception:
                d0 = d1 = None
            if d0:
                # L-21A: Form 3 start, appointment within 45 days
                if rule.startswith(("L-X3", "L-X5")) and earliest_form.startswith("3"):
                    for d_, t_ in ev_dates:
                        try:
                            dd = abs((date.fromisoformat(d_[:10]) - d0).days)
                        except Exception:
                            continue
                        if t_ == "appointment" and dd <= 45:
                            return "same", ev + f"; L-21A: the anchoring CIK's earliest row at this issuer is a Form {earliest_form} (period {w[0][:10]}), so the insider relationship began then, and the 8-K appointment is {dd} day(s) away", \
                                "L-21A Form 3 initial-statement date anchor (role not consulted)"
                # L-21B: 8-K event inside the CIK's reporting window
                if rule.startswith(("L-X3", "L-X5")):
                    for d_, t_ in ev_dates:
                        try:
                            d = date.fromisoformat(d_[:10])
                        except Exception:
                            continue
                        if d0 <= d <= d1:
                            return "same", ev + f"; L-21B: the 8-K event date {d_[:10]} falls inside the anchoring CIK's Form 3/4/5 window at this issuer ({w[0][:10]}..{w[1][:10]}), so that person was a reporting insider of this issuer on that date", \
                                "L-21B 8-K event inside the anchor CIK's reporting window"
                # L-21C: the "contradiction" rests on a Form 4 start date
                if rule.startswith("L-X3") and earliest_form.startswith("4"):
                    return "same", ev + f"; L-21C: the anchoring CIK's earliest row at this issuer is a Form {earliest_form}, a change report that presupposes a Form 3 already on file, so it does not date the relationship; the apparent contradiction is this corpus's recent-slice window, not a conflict", \
                        "L-21C timeline contradiction withdrawn (Form 4 does not date the relationship)"
                # L-21E: role disagreement only
                if rule.startswith("L-X5") and middle_relation(a, b) != "conflict" and suffix_relation(a, b) != "conflict":
                    return "same", ev + "; L-21E: the only objection is role disagreement, which research 17 F6 measured on this source as 32 same / 0 different, and which ticket 20 Q3 makes evidence rather than key", \
                        "L-21E role disagreement is not evidence of a different person"
        if rule.startswith("L-X4"):
            return "unknown", ev + "; L-21F: two Form 3/4/5 CIKs carry this surname and given name at this issuer and the only field that separates them is the middle initial, which is the key itself -- settling this pair would re-apply the key", \
                "L-21F unsettled: separable only by the key itself"
    if p["stratum"] == "K":
        evs = p.get("group_events") or []
        types = [e[1] for e in evs]
        if rule.startswith("L-K4") and middle_relation(a, b) != "conflict" and suffix_relation(a, b) != "conflict" \
                and len({e[0] for e in evs}) >= 2 and types and all(t in ("appointment", "departure") for t in types):
            return "same", ev + "; L-21E: the only objection is a role-class difference across a coherent event sequence at one issuer, which research 17 F6 measured as 32 same / 0 different on this source", \
                "L-21E role disagreement is not evidence of a different person"
        if rule.startswith("L-K3"):
            return "unknown", ev + "; L-21F: two Form 3/4/5 CIKs carry this surname and given name at this issuer; separable only by the key itself", \
                "L-21F unsettled: separable only by the key itself"
    return lab, ev, rule


# ============================ run ===============================================================
out = []
for p in pairs:
    lab, ev, rule = draft_17(p)
    p["draft_label"], p["draft_rule"] = lab, rule
    lab, ev, rule = settle_21(p, lab, ev, rule)
    p["label"], p["evidence"], p["labeler_rule"] = lab, ev, rule
    o = overrides.get(p["pair_id"])
    if o:
        p["label"] = o["label"]
        p["evidence"] = ev + " | override: " + o["evidence"]
        p["labeler_rule"] = o.get("rule", "L-OVR my reading")
    out.append(p)

if "--verify" in sys.argv:
    r17 = {json.loads(l)["pair_id"]: json.loads(l) for l in open(c21.HERE / "17-pairs.jsonl")}
    n = bad = 0
    for p in out:
        q = r17.get(p["pair_id"])
        if not q:
            continue
        n += 1
        if q["draft_label"] != p["draft_label"] or q["draft_rule"] != p["draft_rule"]:
            bad += 1
            print("DRAFT MISMATCH", p["pair_id"], q["draft_label"], q["draft_rule"], "!=",
                  p["draft_label"], p["draft_rule"])
    print(f"verify: {n} pairs shared with research 17, {bad} draft-label mismatches")
    if bad:
        sys.exit(1)

with open(c21.HERE / "21-pairs.jsonl", "w") as f:
    for p in out:
        slim = {k: p[k] for k in ("pair_id", "stratum", "source", "ctx", "firm_name", "key_fields",
                                  "match", "key_fixed", "suffix_veto", "roles_consistent",
                                  "label", "evidence", "labeler_rule", "draft_label", "draft_rule",
                                  "r17_labelled")}
        slim["a"] = {k: p["a"][k] for k in ("rec_id", "raw_name", "xref", "filing", "title",
                                            "suffix", "event_type", "date")}
        slim["b"] = {k: p["b"][k] for k in ("rec_id", "raw_name", "xref", "filing", "title",
                                            "suffix", "event_type", "date")}
        for k in ("anchor", "f4_ciks_with_fl", "f4_periods", "f4_all_periods_this_cik",
                  "f4_forms_this_cik", "f4_all_names_this_cik", "group_events", "src_events"):
            if p.get(k) is not None:
                slim[k] = p[k]
        f.write(json.dumps(slim, default=str) + "\n")

print("labels (all 938):", dict(Counter(p["label"] for p in out)))
fx = [p for p in out if p["key_fixed"]]
print("labels at the FIXED key:", len(fx), dict(Counter(p["label"] for p in fx)))
print("rules at the fixed key:", dict(Counter(p["labeler_rule"].split()[0] for p in fx)))
with open(c21.R21 / "draft_review.txt", "w") as f:
    for p in out:
        if p["label"] != "same":
            f.write(f"{p['pair_id']} [{p['label']}] {p['labeler_rule']} key_fixed={p['key_fixed']}\n"
                    f"   A '{p['a']['raw_name']}' {p['a']['title'][:40]} | B '{p['b']['raw_name']}' ({p['b']['xref']}) {p['b']['title'][:40]}\n"
                    f"   {p['evidence'][:500]}\n")
