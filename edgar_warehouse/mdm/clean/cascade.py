"""The cascade: SEC-to-GLEIF matching passes, strict to loose (ticket 21).

Operator, 2026-09-27: "match on name and address first, if it matches merge
it ... then reduce the fields gradually until you get more merging", with no
jurisdiction test. Each pass compares the name (legal form kept, GLEIF other
names counted) and fewer address parts than the one before. It takes only the
SEC filers and GLEIF entities no earlier pass bound, and binds a pair only
one to one in that pass: the filer agrees with exactly one entity, and that
entity with exactly one filer.

It runs once over both whole sources, never over what a Stage holds, so load
order cannot change a result: the Name Census carries its answer per CIK
(`name_census.py`) and the Merge Stage re-checks each pair on its own rows
(`matching.py`). The proof calls this same function, so it measures what runs.

Addresses are the ones the data quality rule leaves fit (ticket 22): GLEIF's
headquarters address first, else its legal address; SEC's business address.
A withheld address, or one more than `over_shared` entities use, is compared
by its country only.

Each bound pair carries flags the proof samples as their own strata
(operator, 2026-09-28): a conflict in place of incorporation ("They both may
be true"), and a name another candidate also holds: another SEC filer the
quality rule left, or another eligible GENERAL GLEIF entity.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from collections.abc import Iterable
from dataclasses import dataclass

from .names import (
    edgar_jurisdiction,
    jurisdictions_conflict,
    legal_form_key,
    postal_codes_agree,
    sec_legal_form_key,
)
from .quality import withheld
from .store import Conflict

VERSION = "sec-gleif-cascade-v1"
TEST = "cascade_pass@1"
CONFLICT = "incorporation conflicts"
NOT_UNIQUE = "name held by another candidate"
PARTS = ("street", "city", "postcode")


@dataclass(frozen=True)
class Place:
    """An address as a pass compares it. `key` (first street line, 5-digit
    postcode, country) counts how many entities share it."""

    street: frozenset
    city: str
    postcode: str | None
    country: str | None
    key: tuple | None


def place(std: dict | None) -> Place:
    """A standardized address (the quality rule's `matching` copy) as a Place."""
    std = std or {}
    lines = [line for part in ("street", "street2") for line in str(std.get(part) or "").split("\n") if line]
    postcode, country = std.get("postcode"), std.get("country")
    key = (lines[0], str(postcode or "")[:5], country or "") if lines else None
    return Place(frozenset(lines), std.get("city") or "", postcode, country, key)


def fit_place(record: dict, matching: dict, names: Iterable[str] = ("headquarters_address", "address")) -> Place:
    """The first of `names` the quality rule left fit to match on; else only
    the country of the first address that has one."""
    country = None
    for name in names:
        std = matching.get(name) or {}
        country = country or std.get("country")
        if std.get("street") and not withheld(record, f"matching.{name}"):
            return place(std)
    return place({"country": country})


@dataclass(frozen=True)
class Filer:
    cik: str
    key: str  # the current name, legal form kept
    place: Place
    incorporated: str | None  # as GLEIF writes a jurisdiction
    business_country: str | None


@dataclass(frozen=True)
class Entity:
    lei: str
    keys: frozenset  # the legal and other names, legal form kept
    place: Place
    jurisdiction: str | None
    eligible: bool  # GENERAL, ACTIVE, not DUPLICATE or ANNULLED
    last_update: str
    legal: str = ""  # the legal name's key: the one name the Stage record holds


def field_value(record: dict, field: str):
    """A Stage record's value for one field; None unless it states a value."""
    item = (record.get("fields") or {}).get(field) or {}
    return item.get("value") if item.get("op") == "value" else None


def matching_values(record: dict) -> dict:
    return (record.get("provenance") or {}).get("matching") or {}


_value, _matching = field_value, matching_values


def filer_of(record: dict) -> Filer:
    """An SEC Company record, as the Stage holds it, as the cascade reads it:
    its business address, never its mailing address."""
    return Filer(
        cik=record["record_key"],
        key=sec_legal_form_key(_value(record, "name")),
        place=fit_place(record, _matching(record), ("address",)),
        incorporated=edgar_jurisdiction(_value(record, "state_of_incorporation")),
        business_country=_matching(record).get("business_country"),
    )


def entity_of(record: dict, keys: frozenset, *, eligible: bool) -> Entity:
    """A GLEIF record, as the Stage holds it, as the cascade reads it. `keys`
    are its legal and other names (the Stage record carries only the legal
    one); `eligible` is the rule's own eligibility test."""
    return Entity(
        lei=(record.get("identifiers") or {}).get("lei"),
        keys=keys | {legal_key(record)} - {""},
        place=fit_place(record, _matching(record)),
        jurisdiction=_value(record, "jurisdiction"),
        eligible=eligible,
        last_update=_value(record, "gleif_last_update") or "",
        legal=legal_key(record),
    )


def legal_key(record: dict) -> str:
    """A GLEIF record's legal name, legal form kept."""
    return legal_form_key(_value(record, "name"))


def record(key: str, fields: dict, matching: dict, quality: dict | None, identifiers: dict | None = None) -> dict:
    """Mapped values in the shape the Stage holds a record, so the census
    reads every filer and entity as the Merge Stage reads its own rows."""
    return {"record_key": key, "identifiers": identifiers or {},
            "fields": {name: {"op": "value", "value": v} for name, v in fields.items()},
            "provenance": {"matching": matching, "quality": quality or {}}}


def spec(policy: dict) -> dict:
    """The passes, in the order the Company rules declare them, with the one
    over-shared threshold and eligibility they all state."""
    passes, shared, eligibility = [], set(), set()
    for rule in (policy.get("kinds") or {}).get("company", {}).get("rules") or []:
        tests = {t["primitive"]: t.get("args") or {} for t in rule.get("when") or []}
        if TEST not in tests:
            continue
        args = tests[TEST]
        if not {"pass", "compare", "over_shared"} <= set(args):
            raise Conflict(f"Cascade rule {rule.get('rule_id')} must state its pass, parts and threshold")
        passes.append({"pass": args["pass"], "compare": args["compare"], "rule_id": rule["rule_id"]})
        shared.add(args["over_shared"])
        found = tests.get("gleif_entity_eligible@1") or {}
        eligibility.add((tuple(found.get("entity_statuses") or ()),
                         tuple(found.get("refused_registration_statuses") or ())))
    if len({p["pass"] for p in passes}) != len(passes) or len(shared) > 1 or len(eligibility) > 1:
        raise Conflict("Cascade passes must be unique and state one threshold and one eligibility")
    statuses, refused = next(iter(eligibility)) if eligibility else ((), ())
    return {"version": VERSION, "passes": passes, "over_shared": next(iter(shared)) if shared else None,
            "entity_statuses": list(statuses), "refused_registration_statuses": list(refused)}


def eligible(values: dict, cascade: dict) -> bool:
    """GLEIF's entity and registration status against the passes' test.
    Only a GENERAL record reaches here: no other category is a Company."""
    return (values.get("gleif_entity_status") in cascade["entity_statuses"]
            and values.get("gleif_registration_status") not in cascade["refused_registration_statuses"])


def entry(census: dict, cik: str, *, census_digest: str) -> dict | None:
    """What one SEC record carries: the census's cascade answer for its CIK."""
    found = ((census.get("cascade") or {}).get("assignments") or {}).get(cik)
    if found is None:
        return None
    return {"census": census_digest, "version": census["cascade"]["version"], **found}


def count_addresses(places: Iterable[Place]) -> Counter:
    return Counter(p.key for p in places if p.key)


def agrees(sec: Place, gleif: Place, compare: list[str] | None) -> bool:
    """Whether two places agree on a pass's parts. `None`: the name alone;
    `[]`: the country alone."""
    if compare is None:
        return True
    if not sec.country or sec.country != gleif.country:
        return False
    for part in compare:
        if part not in PARTS:
            raise ValueError(f"A pass compares an unknown address part: {part}")
        if part == "street" and not sec.street & gleif.street:
            return False
        if part == "city" and not (sec.city and sec.city == gleif.city):
            return False
        if part == "postcode" and not postal_codes_agree(sec.postcode, sec.country, gleif.postcode, gleif.country):
            return False
    return True


def _usable(p: Place, counts: Counter, over_shared: int) -> Place:
    if p.key and counts[p.key] > over_shared:
        return place({"country": p.country})
    return p


def assign(
    filers: Iterable[Filer],
    entities: Iterable[Entity],
    passes: list[dict],
    *,
    address_counts: Counter,
    over_shared: int,
) -> dict[str, dict]:
    """CIK -> the LEI the passes bind it to, the pass, its last update and
    its flags. `address_counts` counts every entity of both whole sources,
    not only those given here."""
    filers = {f.cik: f for f in filers}
    entities = {e.lei: e for e in entities}
    by_key, holders = defaultdict(set), defaultdict(set)
    for f in filers.values():
        by_key[f.key].add(f.cik)
    for e in entities.values():
        for key in e.keys:
            holders[key].add(e.lei)
    sec_place = {c: _usable(f.place, address_counts, over_shared) for c, f in filers.items()}
    gleif_place = {l: _usable(e.place, address_counts, over_shared) for l, e in entities.items()}
    found: dict[str, dict] = {}
    taken: set[str] = set()
    for step in passes:
        proposals, claims = defaultdict(set), defaultdict(set)
        for cik, f in sorted(filers.items()):
            if cik in found or not f.key:
                continue
            for lei in holders.get(f.key, ()):
                e = entities[lei]
                if lei in taken or not e.eligible:
                    continue
                if agrees(sec_place[cik], gleif_place[lei], step["compare"]):
                    proposals[cik].add(lei)
                    claims[lei].add(cik)
        for cik, leis in sorted(proposals.items()):
            if len(leis) != 1 or len(claims[next(iter(leis))]) != 1:
                continue
            lei = next(iter(leis))
            f, e = filers[cik], entities[lei]
            flags = []
            if jurisdictions_conflict(f.incorporated, e.jurisdiction, sec_business_country=f.business_country):
                flags.append(CONFLICT)
            if len(by_key[f.key]) > 1 or sum(entities[h].eligible for h in holders[f.key]) > 1:
                flags.append(NOT_UNIQUE)
            found[cik] = {"lei": lei, "last_update": e.last_update, "pass": step["pass"], "flags": flags,
                          "key": f.key, "via": "legal name" if e.legal == f.key else "other name"}
            taken.add(lei)
    return found
