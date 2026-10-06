"""What a name rule must respect, learnt from the data (profiling ticket 07b; plan decision 26).

A name rule needs more than a fixed precision bar (operator, 2026-10-06: "name
with class A is completely different from class C"). The data says which parts
of a name matter:

- **Distinguishing tokens.** Two records with different keys whose names
  differ in one token only ("<x> fund class a" and "<x> fund class c") show
  that the token tells entities apart. A rule must compare it exactly.
- **Equivalent variants.** Two names of one record (a former name, another
  name, or the same entity in a second source, decided by a shared id) that
  differ in a token or two show variants a rule may fold ("corp" and
  "corporation", a dropped suffix).
- **Conflicts.** A token pair that is both is a rule's danger: the name alone
  cannot decide, so a supporting attribute must.
- **Supporting attributes.** On pairs a shared id proves are one entity, how
  often each attribute agrees; on near-homonyms (different entities, names
  equal once folded), how often it tells them apart.
- **Homonym risk.** How many folded names more than one entity holds.

Every count comes from the data with examples; nothing here names a source,
a kind or a language's legal forms. A name is the last resort (operator,
2026-10-06): used only where no id exists, as an id made from it.
"""

from __future__ import annotations

import csv
import difflib
import hashlib
import os
import re
import tempfile
from collections import Counter, defaultdict
from dataclasses import dataclass, field

from .names import name_norm

TOKEN_NORMALIZATION = "tokens@1: name_norm, then split on every run of characters that is not a letter or a digit"
ROMAN = re.compile(r"^(?=[ivxlcdm]+$)m{0,3}(cm|cd|d?c{0,3})(xc|xl|l?x{0,3})(ix|iv|v?i{0,3})$")
# A token pair seen at least this often is reported; rarer ones are noise.
MIN_SUPPORT = 2
EXAMPLES = 3
# A skeleton shared by more names than this is too generic to learn from.
MAX_GROUP = 50


def tokens(value: str) -> list[str]:
    return [t for t in re.split(r"[^\w]+|_", name_norm(value)) if t]


def token_class(token: str) -> str:
    """The shape of a token: what a rule would generalise over."""
    if token.isdigit():
        return "number"
    if len(token) == 1 and token.isalpha():
        return "letter"
    if ROMAN.match(token):
        return "roman"
    return "word"


@dataclass
class Evidence:
    """Counts with a few examples each."""

    counts: Counter = field(default_factory=Counter)
    examples: dict = field(default_factory=lambda: defaultdict(list))

    def add(self, key, example) -> None:
        self.counts[key] += 1
        if len(self.examples[key]) < EXAMPLES:
            self.examples[key].append(example)

    def top(self, n: int = 25, min_support: int = MIN_SUPPORT) -> list[dict]:
        return [{"pair" if isinstance(k, tuple) else "token": list(k) if isinstance(k, tuple) else k,
                 "count": c, "examples": self.examples[k]}
                for k, c in self.counts.most_common() if c >= min_support][:n]


def distinguishing(con, records) -> Evidence:
    """Token pairs that tell two records apart, keys different.

    `records` are (key, name) for one source's current names; `con` is a DuckDB
    connection. Each name stands for each of its tokens in turn, replaced by a
    gap; names sharing that skeleton with a different key and a different
    token at the gap give the pair, with the token before the gap ("^" at the
    start) as its context. A name that is another record's name less one token
    gives the pair ("", token): that token's drop tells them apart. A skeleton
    shared by more than MAX_GROUP names is too generic to learn from."""
    with tempfile.NamedTemporaryFile("w", suffix=".csv", newline="", delete=False) as handle:
        writer = csv.writer(handle)
        writer.writerow(["key", "toks", "name"])
        for key, name in records:
            parts = tokens(name)
            if parts:
                writer.writerow([key, " ".join(parts), name])
        path = handle.name
    try:
        rows = con.execute(f"""
            WITH n AS (SELECT key, toks, string_split(toks, ' ') AS a, name
                         FROM read_csv(?, header=true, all_varchar=true, quote='"')),
            s AS (SELECT key, name, a[i] AS tok, CASE WHEN i > 1 THEN a[i - 1] ELSE '^' END AS ctx,
                         array_to_string(a[1:i - 1], ' ') || ' _ ' || array_to_string(a[i + 1:], ' ') AS skel,
                         array_to_string(list_concat(a[1:i - 1], a[i + 1:]), ' ') AS rest
                    FROM n, range(1, len(a) + 1) r(i)
                   WHERE len(a) >= 2),
            g AS (SELECT skel FROM s GROUP BY skel
                   HAVING count(DISTINCT key) >= 2 AND count(DISTINCT tok) >= 2 AND count(*) <= {MAX_GROUP}),
            p AS (SELECT x.tok AS a, y.tok AS b, x.skel, x.ctx, x.name AS na, y.name AS nb
                    FROM s x JOIN s y ON x.skel = y.skel AND x.tok < y.tok AND x.key <> y.key
                   WHERE x.skel IN (SELECT skel FROM g)),
            d AS (SELECT '' AS a, s.tok AS b, s.skel, s.ctx, s.name AS na, m.name AS nb
                    FROM s JOIN n m ON s.rest = m.toks AND s.key <> m.key),
            q AS (SELECT *, row_number() OVER (PARTITION BY a, b ORDER BY skel, na, nb) AS rn
                    FROM (SELECT * FROM p UNION ALL SELECT * FROM d))
            SELECT a, b, count(DISTINCT skel) AS c,
                   list({{'context': ctx, 'names': [na, nb]}} ORDER BY rn) FILTER (WHERE rn <= {EXAMPLES}) AS ex
              FROM q GROUP BY a, b""", [path]).fetchall()
    finally:
        os.unlink(path)
    found = Evidence()
    for a, b, count, examples in rows:
        found.counts[(a, b)] = count
        found.examples[(a, b)] = [dict(e) for e in examples]
    return found


def variants(pairs: list[tuple[str, str]], max_changed: int = 2) -> Evidence:
    """Token pairs two names of one entity differ by: (a, b), or (a, "") for a
    token one name drops. Pairs differing in more than `max_changed` tokens, or
    sharing under half their tokens, are a rename, not a variant."""
    found = Evidence()
    for left, right in pairs:
        a, b = tokens(left), tokens(right)
        if not a or not b or a == b:
            continue
        matcher = difflib.SequenceMatcher(a=a, b=b, autojunk=False)
        shared = sum(block.size for block in matcher.get_matching_blocks())
        if shared * 2 < max(len(a), len(b)):
            continue
        changes = [op for op in matcher.get_opcodes() if op[0] != "equal"]
        if sum(max(i2 - i1, j2 - j1) for _, i1, i2, j1, j2 in changes) > max_changed:
            continue
        for _, i1, i2, j1, j2 in changes:
            x, y = " ".join(a[i1:i2]), " ".join(b[j1:j2])
            found.add(tuple(sorted((x, y))), {"names": [left, right]})
    return found


def conflicts(apart: Evidence, alike: Evidence) -> list[dict]:
    """Token pairs that tell entities apart in some records and are mere variants in others."""
    both = set(apart.counts) & set(alike.counts)
    return sorted(({"pair": list(p), "apart": apart.counts[p], "alike": alike.counts[p],
                    "apart_examples": apart.examples[p], "alike_examples": alike.examples[p]}
                   for p in both), key=lambda r: -(r["apart"] + r["alike"]))


def by_class(apart: Evidence) -> list[dict]:
    """The distinguishing pairs grouped by the token classes and the token before them."""
    grouped: Counter = Counter()
    examples: dict = defaultdict(list)
    for pair, count in apart.counts.items():
        if count < MIN_SUPPORT:
            continue
        shape = tuple(sorted(token_class(t) for t in pair))
        contexts = Counter(e["context"] for e in apart.examples[pair])
        key = (shape, contexts.most_common(1)[0][0])
        grouped[key] += count
        if len(examples[key]) < EXAMPLES:
            examples[key].append(list(pair))
    return [{"classes": list(k[0]), "after": k[1], "count": c, "pairs": examples[k]}
            for k, c in grouped.most_common(25)]


def homonyms(records: list[tuple[str, str]]) -> dict:
    """How many folded names more than one key holds, with examples."""
    holders: dict[str, set] = defaultdict(set)
    for key, name in records:
        folded = " ".join(tokens(name))
        if folded:
            holders[folded].add(key)
    shared = {n: k for n, k in holders.items() if len(k) > 1}
    return {"names": len(holders), "held_by_more_than_one": len(shared),
            "rate": round(len(shared) / len(holders), 6) if holders else 0.0,
            "examples": [{"name": n, "holders": len(k)} for n, k in sorted(shared.items(), key=lambda i: -len(i[1]))[:EXAMPLES]]}


def _folded(value) -> str:
    return re.sub(r"[^0-9a-z]", "", str(value or "").lower())


def agree(left, right) -> bool | None:
    """Equal once folded to letters and digits, or one the start of the other
    (a longer postcode, a coded region); None when either is empty."""
    a, b = _folded(left), _folded(right)
    if not a or not b:
        return None
    return a == b or a.startswith(b) or b.startswith(a) or a.endswith(b) or b.endswith(a)


def support(same: list[tuple[dict, dict]], near: list[tuple[dict, dict]], attributes: list[tuple[str, str]]) -> list[dict]:
    """Per attribute pair: how often it agrees on pairs proved one entity, and
    how often it tells near-homonyms apart (disagrees on different entities
    whose folded names are equal). Unfilled values are counted apart."""
    found = []
    for left, right in attributes:
        on_same = [agree(a.get(left), b.get(right)) for a, b in same]
        on_near = [agree(a.get(left), b.get(right)) for a, b in near]
        filled_same = [x for x in on_same if x is not None]
        filled_near = [x for x in on_near if x is not None]
        found.append({
            "left": left, "right": right,
            "agrees_on_same": round(sum(filled_same) / len(filled_same), 4) if filled_same else None,
            "same_compared": len(filled_same), "same_unfilled": len(on_same) - len(filled_same),
            "separates_near_homonyms": round(sum(not x for x in filled_near) / len(filled_near), 4) if filled_near else None,
            "near_compared": len(filled_near),
        })
    return found


def proposal(apart: Evidence, alike: Evidence, clashes: list[dict], attributes: list[dict], risk: dict) -> dict:
    """What a rule built on this data must do, in plain words, for the operator to rule on."""
    foldable = [{"pair": list(p), "count": c} for p, c in alike.counts.most_common()
                if c >= MIN_SUPPORT and p not in apart.counts][:25]
    useful = [a for a in attributes if (a["agrees_on_same"] or 0) >= 0.95 and (a["separates_near_homonyms"] or 0) >= 0.5]
    return {
        "compare_exactly": by_class(apart),
        "may_fold": foldable,
        "needs_a_supporting_attribute": [c["pair"] for c in clashes[:25]],
        "supporting_attributes": [f"{a['left']} = {a['right']}" for a in useful],
        "homonym_rate": risk["rate"],
        "note": ("A token pair under compare_exactly tells entities apart in this data: a rule that "
                 "folds it merges different entities. A pair under needs_a_supporting_attribute is "
                 "both, so the name cannot decide. A name is used only where no id exists, as the id "
                 "made from it (name_id), and joins only where one record on each side holds it."),
    }


# -- An id made from a name, for records that carry no id at all ---------------
#
# Operator, 2026-10-06: "Use name matching only when every thing else is not an
# option no id exists you just need to create a id using name". `name_id@1`
# keeps every token and folds nothing: the variants the data shows on one
# entity, and never apart, are reported as evidence for a later version.

NAME_ID = ("name_id@1: tokens@1 joined by one space, the sha256 of 'name_id@1', 0x1F and that text; every token kept. "
           "It is the engine's cross-reference format name_id@1, so a contract fills it with no code")


def folds(alike: Evidence, apart: Evidence) -> list[tuple[str, str]]:
    """The variants to fold, longest first: (spelling, replacement); a dropped
    token folds to nothing. Only pairs seen on one entity and never apart."""
    found = []
    for (a, b), count in alike.counts.items():
        if count < MIN_SUPPORT or (a, b) in apart.counts:
            continue
        if not a or not b:
            found.append((a or b, ""))
        else:
            found.append((a, b) if len(a) <= len(b) else (b, a))
    return sorted(found, key=lambda f: (-len(f[0].split()), f[0]))


def name_key(value: str, rules: list[tuple[str, str]]) -> str:
    text = f" {' '.join(tokens(value))} "
    for spelling, replacement in rules:
        text = text.replace(f" {spelling} ", f" {replacement} " if replacement else " ")
    return " ".join(text.split())


def name_id(value: str) -> str | None:
    """The engine's `name_id@1` cross-reference format, computed the same way."""
    key = " ".join(tokens(value))
    return hashlib.sha256(f"name_id@1\x1f{key}".encode()).hexdigest() if key else None


def join_by_name(left: list[tuple[str, str]], right: list[tuple[str, str]], rules: list[tuple[str, str]]) -> dict:
    """Records of two sources joined by their name id, only where it is held by
    exactly one record on each side; a name id held twice joins nothing."""
    sides = []
    for records in (left, right):
        held: dict[str, set] = defaultdict(set)
        for key, name in records:
            folded = name_key(name, rules)
            if folded:
                held[folded].add(key)
        sides.append(held)
    joined = {n: (next(iter(sides[0][n])), next(iter(sides[1][n])))
              for n in sides[0].keys() & sides[1].keys() if len(sides[0][n]) == 1 and len(sides[1][n]) == 1}
    ambiguous = [n for n in sides[0].keys() & sides[1].keys() if len(sides[0][n]) > 1 or len(sides[1][n]) > 1]
    return {"joined": joined, "ambiguous": ambiguous}
