"""A small synthetic data set for the data-profiling tests (no real source)."""

import csv
import random
from pathlib import Path

NAMES = ["Ann", "Bo", "Cy", "Di", "Ed", "Flo", "Gus", "Hal", "Ida", "Jo"]
FAMILY = ["Ray", "Sun", "Oak", "Lee", "Fox", "Day", "Hill", "Moss"]


def _write(path: Path, header: list[str], rows: list[list]) -> None:
    with path.open("w", newline="") as handle:
        out = csv.writer(handle)
        out.writerow(header)
        out.writerows(rows)


def build(folder: Path) -> Path:
    """Writes one CSV per part into `folder` and returns it.

    member     master: dense counter key, personal columns, a group code
    grp        reference: 12 codes with labels and a parent code (roots empty)
    item       master: an issued code, a two-level category nested in its code
    visit      transaction: one event per row, ~95% of member keys known
    line       transaction: (visit_id, line_no) per visit
    pairing    relationship: two members and a role
    """
    rng = random.Random(11)
    folder.mkdir(parents=True, exist_ok=True)
    groups = [[f"G{n:02d}", f"Group {n}", "" if n <= 3 else f"G{(n - 1) % 3 + 1:02d}"] for n in range(1, 13)]
    _write(folder / "grp.csv", ["grp_code", "grp_label", "parent_grp_code"], groups)
    members = [[i, rng.choice(NAMES), rng.choice(FAMILY), f"19{rng.randint(50, 99)}-0{rng.randint(1, 9)}-1{rng.randint(0, 9)}",
                rng.choice(groups)[0], f"{rng.randint(1, 99)} Main St"] for i in range(1, 301)]
    _write(folder / "member.csv", ["member_id", "given_name", "surname", "birth_date", "grp_code", "street_address"], members)
    cats = {f"{a}{b}": (f"{a}", f"Top {a}", f"Sub {a}{b}") for a in range(1, 5) for b in range(1, 4)}
    items = []
    for n in range(1, 121):
        sub = rng.choice(sorted(cats))
        top, top_label, sub_label = cats[sub]
        items.append([f"IT{n:06d}", f"Thing {n}", top, top_label, sub, sub_label, round(rng.uniform(1, 50), 2)])
    _write(folder / "item.csv", ["item_code", "item_name", "cat", "cat_label", "sub_cat", "sub_cat_label", "weight"], items)
    visits = []
    for v in range(1, 3001):
        member = rng.randint(1, 300) if rng.random() > 0.05 else rng.randint(301, 330)
        visits.append([v, member, f"2025-{rng.randint(1, 12):02d}-{rng.randint(1, 28):02d}", round(rng.uniform(1, 500), 2)])
    _write(folder / "visit.csv", ["visit_id", "member_id", "visited_on", "amount"], visits)
    lines = [[v, n, rng.choice(items)[0], rng.randint(1, 9)] for v in range(1, 3001) for n in range(1, rng.randint(2, 4))]
    _write(folder / "line.csv", ["visit_id", "line_no", "item_code", "qty"], lines)
    pairs = set()
    while len(pairs) < 200:
        a, b = rng.sample(range(1, 301), 2)
        pairs.add((a, b, rng.choice(["guardian", "partner"])))
    _write(folder / "pairing.csv", ["member_a", "member_b", "role"], sorted(pairs))
    return folder
