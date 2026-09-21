"""Research 21: shared pieces. Thin layer on research 17's `17-common.py`.

Research 21 is a continuation of research 17, not a new study: the record table
(`r17/records.parquet`), the normalizers, the name parsers, the role classes and the Wilson
arithmetic are research 17's, imported unchanged. What this module adds is exactly one thing —
the **fixed Tier B key** that ticket 20 Q3 settled, which research 17 did not score as a single
key:

    same issuer identity  AND  surname + given name + middle initial (`mi`)
                          AND  no generational-suffix conflict (a hard veto)

Research 17's `mi` variant is suffix-*insensitive*: `k_mi` is `LAST|FIRST|M`, so
`FLORSHEIM THOMAS W JR` and `FLORSHEIM THOMAS W` share it. Ticket 20 Q3 point 3 makes a
generational suffix present on one side only a **conflict**, not a normalization step, so the
fixed key is `mi` **minus** every pair whose generational-suffix sets differ.

Sockets are blocked at import (inherited from 17-common); `21-iapd.py` would be the only script
allowed to re-enable them, under its own request log.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

HERE = Path(__file__).resolve().parent
_spec = importlib.util.spec_from_file_location("c17", HERE / "17-common.py")
c17 = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(c17)

R17 = c17.R17                     # research 17's scratchpad dir (records.parquet lives here)
R21 = c17.SCRATCH / "r21"

# Ticket 20 Q3 point 3 names exactly these five tokens.
GEN_SUFFIXES = ("JR", "SR", "II", "III", "IV")
# research 17's own GEN list additionally carried "V"; `gen_set_17` exists so the study can
# report whether including it changes any decision (it does not -- see the findings).
GEN_SUFFIXES_17 = GEN_SUFFIXES + ("V",)


def gen_set(suffix_field: str, tokens=GEN_SUFFIXES) -> frozenset:
    """The generational-suffix tokens in a record's parsed `suffix` field.

    `suffix_field` is the space-joined suffix list research 17's parsers produced, which also
    holds credential tokens (CFA, PHD, ...). Only generational tokens participate in the veto.
    """
    return frozenset(t for t in (suffix_field or "").split(" ") if t in tokens)


def suffix_veto(sa: str, sb: str, tokens=GEN_SUFFIXES) -> bool:
    """True when ticket 20's hard veto fires: the two generational-suffix sets are not equal.

    Covers both cases the ticket names -- a conflicting suffix (`JR` vs `III`) and a suffix on
    one side only (`JR` vs absent). Absent on both is not a veto.
    """
    return gen_set(sa, tokens) != gen_set(sb, tokens)


def fixed_key_match(a_k_mi: str, b_k_mi: str, a_suffix: str, b_suffix: str,
                    tokens=GEN_SUFFIXES) -> bool:
    """Ticket 20 Q3's key, scored exactly as written (the issuer-identity component is applied
    upstream: every pair in this study is two records at one issuer CIK)."""
    return a_k_mi == b_k_mi and not suffix_veto(a_suffix, b_suffix, tokens)


def n_for_lcb(target: float, z: float, errors: int = 0) -> int:
    """Smallest n whose Wilson lower bound clears `target` with exactly `errors` errors.

    Same arithmetic as research 17's `n_for_lcb`, started at n = errors + 1 rather than n = 1:
    17's version evaluates k = n - errors at n = 1, which is negative for errors >= 2 and raises
    a domain error inside the square root. Identical output for errors in (0, 1).
    """
    n = max(1, errors + 1)
    while c17.wilson_lower(n - errors, n, z) < target:
        n += 1
        if n > 100000:
            return -1
    return n
