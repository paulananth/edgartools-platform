"""Ticket 84: how many CUSIP Securities change name when OpenFIGI ranks first (counts only).

    python name_change_count.py OPENFIGI.jsonl NPORT.jsonl THIRTEENF.jsonl OUT.json

Inputs are dump_readings.py's rows of the configured readings. A Security's name before: 13F's
lexically first filed name, else N-PORT's (the old order, each reduction keeping the lexically
first member). After: OpenFIGI's name where its listings state exactly one (combine.yaml), else
N-PORT's, else 13F's.
"""
import json
import re
import sys
from collections import defaultdict

fold = re.compile(r"[\W_]+")


def norm(v):
    return fold.sub(" ", v).strip().upper()


def names(path, key, column):
    found = defaultdict(set)
    with open(path) as rows:
        for line in rows:
            r = json.loads(line)
            if r.get(key) and r.get(column):
                found[r[key].upper()].add(r[column])
    return found


figi, nport, thirteenf = (names(sys.argv[1], "id", "name"), names(sys.argv[2], "cusip", "issuer_name"),
                          names(sys.argv[3], "cusip", "issuer_name"))
counts = defaultdict(int)
for cusip in set(nport) | set(thirteenf):
    before = min(thirteenf[cusip]) if cusip in thirteenf else min(nport[cusip])
    one = figi.get(cusip) if figi.get(cusip) and len(figi[cusip]) == 1 else None
    after = next(iter(one)) if one else (min(nport[cusip]) if cusip in nport else min(thirteenf[cusip]))
    counts["securities"] += 1
    counts["name_from_openfigi"] += bool(one)
    counts["openfigi_states_two_or_more"] += bool(figi.get(cusip)) and not one
    counts["unchanged"] += after == before
    counts["changed_spelling_only"] += after != before and norm(after) == norm(before)
    counts["changed_words"] += norm(after) != norm(before)
    counts["was_13f_now_nport"] += (not one) and cusip in thirteenf and cusip in nport and after != before
json.dump(dict(counts), open(sys.argv[4], "w"), indent=1, sort_keys=True)
print(json.dumps(dict(counts), indent=1, sort_keys=True))
