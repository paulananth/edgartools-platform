"""Short words for a dated sighting and the period that results.

A pasted sighting may use the words below where a stored key goes. The full
sightings are the same text with each word replaced by its stored key. A stored
key typed bare is refused, since its name does not say what it does. `title`
keeps its name, because the word matches the field. The period words name what
comes out of the fold. They are not typed into a sighting: a period starts at the
first sighting that holds the capacity, and it ends only at a later sighting that
drops it. A missing later file ends nothing.
"""

import json

from edgar_warehouse.mdm.relationships import fold_sightings

SIGHTING = {
    "seen on": "on",
    "still held": "held",
    "how known": "basis",
    "filing id": "assertion_id",
    "filing": "subject",
}
PERIOD = {
    "starts": "valid_from",
    "start known by": "valid_from_basis",
    "ends": "valid_to",
    "end known by": "valid_to_basis",
    "last seen": "last_observed",
    "left for a steward": "contradictions",
}
ENDS = {"ends", "end known by", "valid_to", "valid_to_basis"}
KEPT = {"title"}
REQUIRED = ("seen on", "how known", "filing id")
BASES = ("observed", "stated")

words = [{"word": word, "stored": stored} for table in (SIGHTING, PERIOD) for word, stored in table.items()]


class _Refused(Exception):
    pass


def explain(rule):
    try:
        short = json.loads(rule)
    except (TypeError, ValueError):
        return {"refused": "The short sightings are not JSON."}
    if not isinstance(short, dict) or not isinstance(short.get("sightings"), list):
        return {"refused": "The short sightings are not one JSON object with a `sightings` list."}
    used = []
    try:
        sightings = [_sighting(item, used) for item in short["sightings"]]
        document = {**short, "sightings": sightings}
        fold_sightings(sightings)
    except _Refused as error:
        return {"refused": f"{error} Words this file accepts: {', '.join(item['word'] for item in words)}."}
    except (TypeError, ValueError) as error:
        return {"refused": str(error)}
    return {"lines": used, "document": document}


def _sighting(item, used):
    if not isinstance(item, dict):
        raise _Refused("Each sighting is one JSON object.")
    out = {}
    for key, value in item.items():
        stored = _key(key, used)
        out[stored] = value
    for word in REQUIRED:
        if SIGHTING[word] not in out:
            raise _Refused(f"A sighting needs {', '.join(repr(word) for word in REQUIRED)}; '{word}' is missing.")
    if out["basis"] not in BASES:
        raise _Refused(f"A sighting's basis is one of: {', '.join(BASES)}.")
    if not (out.get("held") is None or isinstance(out["held"], bool)):
        raise _Refused("A sighting's held flag is true, false or null.")
    return out


def _key(key, used):
    if key in SIGHTING:
        _use(used, key, SIGHTING[key])
        return SIGHTING[key]
    if key in KEPT:
        return key
    if key in SIGHTING.values():
        typed = next(word for word, stored in SIGHTING.items() if stored == key)
        raise _Refused(f"'{key}' is a stored key. Type '{typed}' instead.")
    if key in ENDS:
        raise _Refused("An end is not typed. It comes from a later sighting that drops the capacity "
                       "('still held' false); a missing later file leaves it empty.")
    if key in PERIOD or key in PERIOD.values():
        raise _Refused(f"'{key}' describes a period, not a sighting.")
    raise _Refused(f"'{key}' is not a word for a sighting.")


def _use(used, word, stored):
    if not any(item["word"] == word for item in used):
        used.append({"word": word, "stored": stored})
