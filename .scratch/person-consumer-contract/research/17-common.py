"""Shared pieces for research 17 (Tier B compound context key calibration).

Normalizers, name parsing per source format, role classes, Wilson bounds, paths.
Sockets are blocked at import so no script that imports this can reach SEC EDGAR;
`17-iapd.py` is the one script that re-enables them, under its own request log.
"""
from __future__ import annotations

import hashlib
import math
import os
import re
import socket
from pathlib import Path

# --- sockets off by default (research 18's convention) -------------------------------------
if os.environ.get("R17_ALLOW_NET") != "1":
    def _blocked(*a, **k):  # pragma: no cover
        raise RuntimeError("network disabled in research 17 scripts")
    socket.socket = _blocked  # type: ignore[assignment]

SCRATCH = Path("/private/tmp/claude-501/-Users-aneenaananth-projects-edgartools-platform/"
               "448ef2c8-e025-4be6-8aef-0620c44e7a52/scratchpad")
R17 = SCRATCH / "r17"
HERE = Path(__file__).resolve().parent  # .scratch/person-consumer-contract/research

ADV_AUG_AB = SCRATCH / "advx/IA_Schedule_A_B_20260801_20260831.csv"
ADV_AUG_BASE = SCRATCH / "advx/IA_ADV_Base_A_20260801_20260831.csv"
ADV_MAR_AB = SCRATCH / "advx_202603/IA_Schedule_A_B_20260301_20260331.csv"
ADV_MAR_BASE = SCRATCH / "advx_202603/IA_ADV_Base_A_20260301_20260331.csv"
ADV_MAR_1D3 = SCRATCH / "advx_202603/IA_1D3_CIK_20260301_20260331.csv"
ADV_AUG_1D3 = SCRATCH / "advx/IA_1D3_CIK_20260801_20260831.csv"
F4_UNION = SCRATCH / "r07/07-union-corpus.jsonl"          # research 07, 104,970 rows
F4_LEGACY_ROWS = SCRATCH / "r18/legacy_rows.jsonl"         # research 18 F8, has officer_title
F4_PRIMARY_ROWS = HERE / "18-owners.jsonl"                 # research 18, has officer_title
EIGHTK = SCRATCH / "person-research/sec_employment_event.parquet"
PROXY = SCRATCH / "person-research/executive_record.parquet"

SEED = 20260920

# --- normalization ---------------------------------------------------------------------------
SUFFIXES = {"JR", "SR", "II", "III", "IV", "V", "ESQ", "CFA", "CPA", "CFP", "PHD", "MD", "JD",
            "MBA", "DDS", "DO", "PE", "RIA", "CIMA", "AIF", "CLU", "CHFC", "CIC", "PPC"}
DROP_TOKENS = {"NMN"}  # "no middle name" placeholder on ADV Schedule A/B; dropped in every variant
HONORIFICS = {"MR", "MRS", "MS", "MISS", "DR", "PROF", "SIR", "HON", "REV", "SPEAKER", "SENATOR", "GOVERNOR", "GENERAL", "ADMIRAL"}


def norm_name(name: str) -> str:
    """research 18 `norm_name` (18-classify.py:118-123), unchanged."""
    s = (name or "").upper()
    s = s.replace("&", " AND ")
    s = re.sub(r"[.,;:/()'\"\-]", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def _toks(s: str) -> list[str]:
    return [t for t in norm_name(s).split(" ") if t and t not in DROP_TOKENS]


def parse_adv(name: str) -> dict:
    """ADV Schedule A/B `Full Legal Name`: `LAST, FIRST, MIDDLE` (form instruction), also
    `LAST, FIRST MIDDLE` (one comma), `LAST, JR, FIRST, MIDDLE` (suffix as a segment) and a few
    `FIRST MIDDLE LAST` with no comma (3 rows in March)."""
    raw = (name or "").strip()
    segs = [s.strip() for s in raw.split(",")]
    segs = [s for s in segs if s]
    if len(segs) == 1:
        return parse_western(raw)
    seg_toks = [[t for t in _toks(s)] for s in segs]
    # pull suffix segments/tokens out anywhere
    suffix = []
    cleaned = []
    for st in seg_toks:
        keep = [t for t in st if t not in SUFFIXES]
        suffix += [t for t in st if t in SUFFIXES]
        if keep:
            cleaned.append(keep)
    if not cleaned:
        return {"last": "", "first": "", "middle": [], "suffix": suffix, "shape": False}
    last = " ".join(cleaned[0])
    rest = [t for seg in cleaned[1:] for t in seg]
    first = rest[0] if rest else ""
    middle = rest[1:]
    return {"last": last, "first": first, "middle": middle, "suffix": sorted(set(suffix)),
            "shape": bool(last and first)}


def parse_edgar(name: str) -> dict:
    """EDGAR conformed reporting-owner name: `LAST FIRST MIDDLE [SUFFIX]`."""
    toks = _toks(name)
    suffix = sorted({t for t in toks if t in SUFFIXES})
    core = [t for t in toks if t not in SUFFIXES]
    if len(core) < 2:
        return {"last": core[0] if core else "", "first": "", "middle": [], "suffix": suffix,
                "shape": False}
    return {"last": core[0], "first": core[1], "middle": core[2:], "suffix": suffix,
            "shape": all(re.fullmatch(r"[A-Z]+", t) for t in core) and 2 <= len(core) <= 5}


def parse_western(name: str) -> dict:
    """Free-text `First Middle Last [Suffix]` (8-K Item 5.02 / DEF 14A), honorifics stripped."""
    toks = _toks(name)
    toks = [t for t in toks if t not in HONORIFICS]
    suffix = sorted({t for t in toks if t in SUFFIXES})
    core = [t for t in toks if t not in SUFFIXES]
    if len(core) < 2:
        return {"last": core[0] if core else "", "first": "", "middle": [], "suffix": suffix,
                "shape": False}
    return {"last": core[-1], "first": core[0], "middle": core[1:-1], "suffix": suffix,
            "shape": all(re.fullmatch(r"[A-Z]+", t) for t in core) and 2 <= len(core) <= 5}


VARIANTS = ("full", "nosuffix", "mi", "fl")


def name_keys(p: dict) -> dict:
    """The four normalizer variants tested. All are exact-equality keys."""
    mid = " ".join(p["middle"])
    mi = p["middle"][0][0] if p["middle"] else ""
    return {
        "full": f"{p['last']}|{p['first']}|{mid}|{' '.join(p['suffix'])}",
        "nosuffix": f"{p['last']}|{p['first']}|{mid}",
        "mi": f"{p['last']}|{p['first']}|{mi}",
        "fl": f"{p['last']}|{p['first']}",
    }


def block_key(p: dict) -> str:
    """Tier C candidate generator (loosest comparator): same surname + same first initial."""
    return f"{p['last']}|{p['first'][:1]}"


# --- role classes ----------------------------------------------------------------------------
_EXEC = re.compile(r"CHIEF|\bCEO\b|\bCFO\b|\bCCO\b|\bCOO\b|\bCIO\b|\bCTO\b|PRESIDENT|OFFICER|GENERAL COUNSEL|"
                   r"SECRETARY|TREASURER|MANAGING DIRECTOR|PRINCIPAL|CHAIRMAN|CHAIR\b|FOUNDER|\bHEAD\b|"
                   r"PORTFOLIO MANAGER|COUNSEL|CONTROLLER|\bEVP\b|\bSVP\b|\bVP\b")
_GOV = re.compile(r"DIRECTOR|TRUSTEE|MANAGER|MANAGING MEMBER|MANAGING PARTNER|GENERAL PARTNER|BOARD|\bMEMBER|NOMINEE|DESIGNEE|\bCHAIR")


def role_class_text(title: str, default: str = "OWNER_ONLY") -> str:
    """research 16 title classes (EXEC / GOVERNANCE / OWNER_ONLY), extended with 8-K vocabulary.
    ADV `Title or Status` falls back to OWNER_ONLY (a shareholder/member with no role); free-text
    8-K / DEF 14A role phrases fall back to UNK, since an unparsed phrase is not an ownership role."""
    t = norm_name(title or "")
    if not t:
        return "UNK"
    if _EXEC.search(t):
        return "EXEC"
    if _GOV.search(t):
        return "GOVERNANCE"
    return default


def role_set_flags(flag_combo: str) -> set[str]:
    s = set()
    for part in (flag_combo or "").split("+"):
        if part == "officer":
            s.add("EXEC")
        elif part == "director":
            s.add("GOVERNANCE")
        elif part in ("10pct", "other"):
            s.add("OWNER_ONLY")
    return s


def roles_consistent(a: set[str], b: set[str]) -> bool:
    """Consistent = not contradictory: either side unknown/empty, or the classes intersect."""
    a = {x for x in a if x != "UNK"}
    b = {x for x in b if x != "UNK"}
    if not a or not b:
        return True
    return bool(a & b)


# --- statistics --------------------------------------------------------------------------------
Z95 = 1.6448536269514722    # one-sided 95%  (Clean MDM accepted Q11, merge-stage.md:54)
Z975 = 1.959963984540054    # one-sided 97.5% (research 18's z; two-sided 95%)


def wilson_lower(k: int, n: int, z: float) -> float:
    if n == 0:
        return float("nan")
    p = k / n
    den = 1 + z * z / n
    centre = p + z * z / (2 * n)
    rad = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return (centre - rad) / den


def n_for_lcb(target: float, z: float, errors: int = 0) -> int:
    n = 1
    while wilson_lower(n - errors, n, z) < target:
        n += 1
        if n > 100000:
            return -1
    return n


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


# --- free-text name eligibility (8-K / DEF 14A) ---------------------------------------------------
_ROLE_TEXT = re.compile(
    r"\b(CHIEF|OFFICER|PRESIDENT|CHAIRMAN|CHAIR|DIRECTOR|DIRECTORS|EXECUTIVE|FINANCIAL|OPERATING|"
    r"VICE|SENIOR|GENERAL|COUNSEL|SECRETARY|TREASURER|COMMITTEE|COMMITTEES|BOARD|COMPANY|CORPORATION|"
    r"INC|LLC|LTD|CORP|PLAN|EQUITY|INCENTIVE|FORMER|INTERIM|MEMBER|EMPLOYMENT|AGREEMENT|COMPENSATORY|ARRANGEMENT|"
    r"CONTROLLER|ACCOUNTING|MANAGER|MANAGING|GROUP|PARTNERS|CAPITAL|FUND|TRUST|HOLDINGS|"
    r"AND|OF|THE|HIS|HER|PREVIOUS|CEO|CFO|COO|CTO|EVP|SVP|VP|OFFICERS|LEADERSHIP|SEC)\b")


def looks_like_role_text(name: str) -> bool:
    """research 01's 'plausible person name' test: no role vocabulary inside the name field."""
    return bool(_ROLE_TEXT.search(norm_name(name)))
