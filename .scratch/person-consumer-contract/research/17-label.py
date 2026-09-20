"""Research 17, stage 3: label the candidate pairs.

Draft labels come from explicit rules that never read the *key* itself (the key is
firm/issuer + normalized name + role); they read the cross-reference ids, IAPD records,
`Status Acquired`, titles/flags, event dates and the middle-name / suffix *conflict* that the
looser variants ignore. Then `17-overrides.json` (my own reading, one line per pair) is applied
on top and the final `17-pairs.jsonl` is written with `label`, `evidence`, `labeler_rule`.

Labels: same | different | unknown.
"""
from __future__ import annotations

import importlib.util
import json
import re
from datetime import date
from pathlib import Path

spec = importlib.util.spec_from_file_location("c17", Path(__file__).with_name("17-common.py"))
c17 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(c17)

pairs = [json.loads(l) for l in open(c17.R17 / "pairs_draft.jsonl")]
iapd = {}
p = c17.HERE / "17-iapd-results.jsonl"
if p.exists():
    for line in open(p):
        d = json.loads(line)
        iapd[d["owner_id"]] = d
overrides = {}
p = Path(__file__).with_name("17-overrides.json")
if p.exists():
    overrides = json.load(open(p))

NICK = {("FRANK", "FRANCIS"), ("ED", "EDWARD"), ("DAN", "DANIEL"), ("GEORGE", "JORGE"), ("ANDY", "ANDREW"),
        ("BILL", "WILLIAM"), ("BOB", "ROBERT"), ("MIKE", "MICHAEL"), ("JIM", "JAMES"), ("TOM", "THOMAS"),
        ("DICK", "RICHARD"), ("RICK", "RICHARD"), ("STEVE", "STEVEN"), ("STEVE", "STEPHEN"), ("TONY", "ANTHONY"),
        ("CHRIS", "CHRISTOPHER"), ("MATT", "MATTHEW"), ("JEFF", "JEFFREY"), ("KATE", "KATHERINE"), ("BEN", "BENJAMIN"),
        ("JOE", "JOSEPH"), ("DAVE", "DAVID"), ("TIM", "TIMOTHY"), ("KEN", "KENNETH"), ("GREG", "GREGORY"),
        ("PAT", "PATRICK"), ("SAM", "SAMUEL"), ("ALEX", "ALEXANDER"), ("NICK", "NICHOLAS"), ("RON", "RONALD"),
        ("DON", "DONALD"), ("RAY", "RAYMOND"), ("LIZ", "ELIZABETH"), ("BETH", "ELIZABETH"), ("JON", "JONATHAN"),
        ("MAX", "MAXWELL"), ("CHUCK", "CHARLES"), ("ROD", "RODNEY"), ("TED", "THEODORE"), ("NATE", "NATHAN")}


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
    """How the two middle-name fields relate, ignoring the key: equal / absent / initial-of /
    typo / conflict."""
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


def iapd_rel(a, b) -> dict:
    ra, rb = iapd.get(a["xref"]), iapd.get(b["xref"])
    out = {"a_resolves": bool(ra and ra.get("resolves")), "b_resolves": bool(rb and rb.get("resolves"))}
    if out["a_resolves"] and out["b_resolves"]:
        na, nb = ra.get("name") or {}, rb.get("name") or {}
        ma, mb = c17.norm_name(na.get("middleName") or ""), c17.norm_name(nb.get("middleName") or "")
        out["iapd_names"] = [f"{na.get('firstName')} {na.get('middleName')} {na.get('lastName')}",
                             f"{nb.get('firstName')} {nb.get('middleName')} {nb.get('lastName')}"]
        if ma and mb and ma != mb and not (ma[:1] == mb[:1] and (len(ma) == 1 or len(mb) == 1)) and not edit1(ma, mb):
            out["iapd_middle"] = "conflict"
        elif ma == mb:
            out["iapd_middle"] = "equal"
        else:
            out["iapd_middle"] = "compatible"
        fa, fb = set(ra.get("firm_ids") or []), set(rb.get("firm_ids") or [])
        out["shared_firms"] = sorted(fa & fb)
        out["a_firms"], out["b_firms"] = sorted(fa), sorted(fb)

        def begins(r):
            ds = []
            for e in (r.get("employments") or []):
                m = re.match(r"(\d+)/(\d+)/(\d{4})", e.get("begin") or "")
                if m:
                    ds.append(date(int(m.group(3)), int(m.group(1)), int(m.group(2))))
            return min(ds).isoformat() if ds else None
        out["a_first_reg"], out["b_first_reg"] = begins(ra), begins(rb)
        out["a_other"], out["b_other"] = ra.get("otherNames"), rb.get("otherNames")
        out["firm_sets_differ"] = bool(fa != fb)

        def gens(r):
            toks = set()
            for n in [f"{(r.get('name') or {}).get('lastName') or ''}"] + list(r.get("otherNames") or []):
                for t in c17.norm_name(n).split(" "):
                    if t in GEN or t == "3RD":
                        toks.add("III" if t == "3RD" else t)
            return toks
        ga, gb = gens(ra), gens(rb)
        out["suffix_conflict"] = f"{sorted(ga)} vs {sorted(gb)}" if ga != gb else ""

        def shared_begin(r, ctx):
            ds = []
            for e in (r.get("employments") or []):
                if str(e.get("firmId")) == str(ctx):
                    m = re.match(r"(\d+)/(\d+)/(\d{4})", e.get("begin") or "")
                    if m:
                        ds.append(date(int(m.group(3)), int(m.group(1)), int(m.group(2))))
            return min(ds) if ds else None
        sa, sb = shared_begin(ra, a.get("ctx")), shared_begin(rb, a.get("ctx"))
        out["a_shared_begin"], out["b_shared_begin"] = (sa.isoformat() if sa else None), (sb.isoformat() if sb else None)
        out["shared_begin_gap_days"] = abs((sa - sb).days) if sa and sb else None
    return out


def draft(p: dict) -> tuple[str, str, str]:
    a, b = p["a"], p["b"]
    a["ctx"] = b["ctx"] = p["ctx"]
    st = p["stratum"]
    same_id = a["xref"] and a["xref"] == b["xref"]
    if st == "P":
        cor = []
        if a["acquired"] and a["acquired"] == b["acquired"]:
            cor.append(f"Status Acquired equal ({a['acquired']})")
        if a["flag_combo"] and a["flag_combo"] == b["flag_combo"]:
            cor.append(f"flags equal ({a['flag_combo']})")
        if a["title"] and b["title"] and c17.role_class_text(a["title"]) == c17.role_class_text(b["title"]):
            cor.append("title class equal")
        if p["source"] == "f4" and a["sub"] and a["sub"] == b["sub"]:
            cor.append("submissions.json name equal")
        return "same", f"same cross-ref id {a['xref']}; " + ("; ".join(cor) if cor else "no id-independent corroboration"), \
            "L-P1 shared id" + (" + corroboration" if cor else " only")
    if st == "R":
        # same id, names differ under `full`
        mr, sr = middle_relation(a, b), suffix_relation(a, b)
        fa, fb = a["k_fl"].split("|")[1], b["k_fl"].split("|")[1]
        la, lb = a["k_fl"].split("|")[0], b["k_fl"].split("|")[0]
        ev = f"same id {a['xref']}; middle={mr}; suffix={sr}"
        if a["acquired"] and a["acquired"] == b["acquired"]:
            ev += f"; Status Acquired equal ({a['acquired']})"
        if la == lb and fa == fb and mr in ("equal", "absent", "initial-of", "typo") and sr in ("equal", "absent"):
            return "same", ev, "L-R1 same id, name variant (middle/initial/suffix/typo)"
        if la == lb and (fa, fb) in NICK or (fb, fa) in NICK or (la == lb and edit1(fa, fb)):
            return "same", ev + "; nickname/typo of given name", "L-R2 same id, nickname or typo"
        if la != lb and fa == fb:
            return "same", ev + "; surname change, given name kept", "L-R3 same id, surname change (legal name change)"
        if set(a["k_nosuffix"].replace("|", " ").split()) == set(b["k_nosuffix"].replace("|", " ").split()):
            return "same", ev + "; token reorder", "L-R4 same id, token reorder"
        return "unknown", ev + "; names do not reconcile", "L-R5 same id, unexplained name difference (possible reused id)"
    if st == "B" and a["k_fl"] != b["k_fl"]:
        return "different", f"block-level pair (surname + first initial); given names differ: {a['k_fl']} vs {b['k_fl']}", \
            "L-B1 different given names (block-only match)"
    if st in ("H", "B") and p["source"] in ("adv", "f4") and a["xref"] and b["xref"] and a["xref"] != b["xref"]:
        mr, sr = middle_relation(a, b), suffix_relation(a, b)
        ir = iapd_rel(a, b)
        ev = f"ids {a['xref']} vs {b['xref']}; middle={mr}; suffix={sr}; acquired {a['acquired'] or '-'} vs {b['acquired'] or '-'}"
        if ir.get("iapd_names"):
            ev += f"; IAPD names {ir['iapd_names']}; IAPD middle={ir['iapd_middle']}; shared firms={ir['shared_firms']}; first reg {ir.get('a_first_reg')} vs {ir.get('b_first_reg')}"
        elif ir.get("a_resolves") or ir.get("b_resolves"):
            ev += f"; IAPD resolves a={ir['a_resolves']} b={ir['b_resolves']}"
        if mr == "conflict":
            return "different", ev, "L-H1 different ids and conflicting middle names"
        if sr == "conflict":
            return "different", ev, "L-H2 different ids and conflicting generational suffix"
        if sr == "absent":
            return "different", ev + "; generational suffix on one side only, two ids", "L-H2b different ids, generational suffix on one side only (father/son)"
        if ir.get("iapd_middle") == "conflict":
            return "different", ev, "L-H3 IAPD records carry conflicting middle names"
        if p["source"] == "f4":
            # two EDGAR CIKs, same issuer, compatible names: the SEC registers one account per filer
            return "unknown", ev + "; two EDGAR filer accounts", "L-H5 two CIKs, compatible names (unsettled)"
        if ir.get("iapd_names"):
            reasons = []
            if ir.get("suffix_conflict"):
                reasons.append(f"generational suffix in IAPD names/otherNames on one side only ({ir['suffix_conflict']})")
            if ir.get("shared_begin_gap_days") is not None and ir["shared_begin_gap_days"] > 365:
                reasons.append(f"registration at filing firm began {ir['shared_begin_gap_days']} days apart ({ir['a_shared_begin']} vs {ir['b_shared_begin']})")
            if reasons:
                return "different", ev + "; " + "; ".join(reasons), "L-H7 two IAPD-registered individuals with distinct registration histories"
            if ir.get("firm_sets_differ"):
                ev += f"; registration firm sets differ ({ir['a_firms']} vs {ir['b_firms']}) but no suffix conflict and no >1-year gap at the filing firm"
            if ir.get("a_firms") and not ir.get("firm_sets_differ") and (ir.get("shared_begin_gap_days") in (None, 0) or ir["shared_begin_gap_days"] <= 31):
                return "same", ev + "; identical IAPD registration history (same firms, same start), no suffix conflict", \
                    "L-H8 duplicate CRD records with one registration history"
        ev += "; acquired equal" if (a["acquired"] and a["acquired"] == b["acquired"]) else ""
        return "unknown", ev, "L-H6 identical/compatible names, two CRD records; public data cannot settle"
    if st == "B":
        mr, sr = middle_relation(a, b), suffix_relation(a, b)
        ev = f"block-level pair; middle={mr}; suffix={sr}; fl equal={a['k_fl'] == b['k_fl']}"
        if a["xref"] and b["xref"] and a["xref"] == b["xref"]:
            return "same", ev + f"; same id {a['xref']}", "L-P1 shared id"
        if a["k_fl"] != b["k_fl"]:
            return "different", ev + "; given names differ", "L-B1 different given names (block-only match)"
        if mr == "conflict":
            return "different", ev, "L-H1 conflicting middle names"
        return "unknown", ev, "L-B2 name-only, no id"
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
        # role agreement
        src_roles = {c17.role_class_text(t, default="UNK") for _, _, t in (p.get("src_events") or [])} - {"UNK"}
        f4_roles = set()
        for fc in p.get("f4_flags") or []:
            f4_roles |= c17.role_set_flags(fc)
        role_ok = (not src_roles) or bool(src_roles & f4_roles)
        # date agreement: an 8-K appointment date within 45 days of the first Form 3/4 period
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
        # timeline contradiction: Form 3/4/5 filings only end > 400 days before an 8-K appointment,
        # or only begin > 400 days after an 8-K departure
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


out = []
for p in pairs:
    lab, ev, rule = draft(p)
    p["draft_label"], p["draft_rule"] = lab, rule
    p["label"], p["evidence"], p["labeler_rule"] = lab, ev, rule
    p["iapd"] = iapd_rel(p["a"], p["b"]) if p["source"] == "adv" and p["stratum"] in ("H", "B") else None
    o = overrides.get(p["pair_id"])
    if o:
        p["label"] = o["label"]
        p["evidence"] = ev + " | override: " + o["evidence"]
        p["labeler_rule"] = o.get("rule", "L-OVR my reading")
    out.append(p)

with open(c17.HERE / "17-pairs.jsonl", "w") as f:
    for p in out:
        slim = {k: p[k] for k in ("pair_id", "stratum", "source", "ctx", "firm_name", "key_fields", "match", "roles_consistent",
                                  "label", "evidence", "labeler_rule", "draft_label", "draft_rule")}
        slim["a"] = {k: p["a"][k] for k in ("rec_id", "raw_name", "xref", "filing", "month", "title", "acquired", "flag_combo", "event_type", "date")}
        slim["b"] = {k: p["b"][k] for k in ("rec_id", "raw_name", "xref", "filing", "month", "title", "acquired", "flag_combo", "event_type", "date")}
        for k in ("any_match", "anchor", "f4_ciks_with_fl", "f4_periods", "bridge_full_keys", "bridge_ids", "iapd"):
            if p.get(k) is not None:
                slim[k] = p[k]
        f.write(json.dumps(slim, default=str) + "\n")

from collections import Counter
c = Counter((p["stratum"], p["source"], p["label"]) for p in out)
for k in sorted(c):
    print(k, c[k])
# sheets of drafts for review
with open(c17.R17 / "draft_review.txt", "w") as f:
    for p in out:
        if p["stratum"] in ("H", "B", "K", "X") or p["label"] != "same":
            f.write(f"{p['pair_id']} [{p['label']}] {p['labeler_rule']}\n   A '{p['a']['raw_name']}' ({p['a']['xref']}) {p['a']['title'][:40]} | B '{p['b']['raw_name']}' ({p['b']['xref']}) {p['b']['title'][:40]}\n   {p['evidence'][:400]}\n")
