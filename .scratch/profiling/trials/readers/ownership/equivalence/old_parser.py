"""Profiling ticket 07: the two ownership readings against the parser #764
deleted (`edgar_warehouse/parsers/ownership.py`, read from `7f753322^`), on both
local sets. Only the fields both hold are compared; every difference is a named
category with its count. Counts only: no value is printed (the filings name people).

    git show 7f753322^:edgar_warehouse/parsers/ownership.py > <old.py>
    uv run python old_parser.py <old.py> <bronze folder> > old-parser.json

The old parser runs with no submissions lookup (it then reads no other file and
makes no request), so its owner_name is the raw name reversed: owner_name_raw is
compared instead.
"""
import collections, glob, importlib.util, json, re, sys
import xml.etree.ElementTree as ET
from pathlib import Path

from edgar_warehouse.rules import files
from edgar_warehouse.rules.source_engine import SourceEngine

spec = importlib.util.spec_from_file_location("old_ownership", sys.argv[1])
old = importlib.util.module_from_spec(spec); spec.loader.exec_module(old)
BRONZE = Path(sys.argv[2])
RULES = Path(__file__).resolve().parents[6] / "rules/sources/sec.ownership"
XML, SGML = (SourceEngine(files.load(RULES / f"ownership-{s}.yaml")) for s in ("xml", "sgml"))
MARKER = re.compile(r" \[F\d+(,F\d+)*\]$")  # the old parser's footnote marker, "<value> [F1,F2]"


def number(v):
    return None if v in (None, "") else float(v)


def blank(v):
    return None if v in (None, "") else v


def kept(root, table, item, required):
    """Positions (from 1) of the rows the old parser kept: it drops a row missing a required block."""
    return [i for i, t in enumerate(root.findall(f"./{table}/{item}"), 1) if all(t.find(r) is not None for r in required)]


def compare(counts, which, a, b, name):
    counts[(which, name, "equal" if a == b else "differ")] += 1


def run(counts, which, accession, raw, xml_bytes, engine, context):
    try:
        new = engine.read(raw, **({"context": context} if context else {})).tables
    except Exception as exc:
        counts[(which, "reading_refused", type(exc).__name__)] += 1
        return
    was = old.parse_ownership(accession, raw.decode("utf-8", "replace"), "4")
    root = old._ownership_root(raw.decode("utf-8", "replace"))
    counts[(which, "filings", "read")] += 1
    # Reporting owners, in document order.
    owners_new, owners_old = new["reporting_owner"], was["sec_ownership_reporting_owner"]
    compare(counts, which, len(owners_new), len(owners_old), "owner_count")
    for n, o in zip(owners_new, owners_old):
        compare(counts, which, int(n["rpt_owner_cik"]) if n["rpt_owner_cik"] else None, o["owner_cik"], "owner.cik")
        compare(counts, which, blank(n["rpt_owner_name"]), blank(o["owner_name_raw"]), "owner.name_raw")
        for f in ("is_director", "is_officer", "is_ten_percent_owner", "is_other"):
            compare(counts, which, bool(n[f]), o[f], f"owner.{f}")
        compare(counts, which, bool(n["rpt_owner_non_us_address_flag"]), o["address_non_us"], "owner.non_us_address")
        compare(counts, which, blank(n["other_text"]), blank(o["other_text"]), "owner.other_text")
        if "see remarks" in (n["officer_title"] or "").lower():  # the old parser put the remarks there
            counts[(which, "owner.officer_title", "old_replaced_see_remarks_with_remarks")] += 1
        else:
            compare(counts, which, blank(n["officer_title"]), blank(o["officer_title"]), "owner.officer_title")
    # Transactions: the reading keeps every row; the old parser dropped rows missing a block.
    for table, item, new_name, old_name, required, extra in (
        ("nonDerivativeTable", "nonDerivativeTransaction", "non_derivative_transaction", "sec_ownership_non_derivative_txn",
         ("transactionAmounts", "ownershipNature", "postTransactionAmounts"), False),
        ("derivativeTable", "derivativeTransaction", "derivative_transaction", "sec_ownership_derivative_txn",
         ("transactionAmounts", "underlyingSecurity", "ownershipNature", "postTransactionAmounts"), True)):
        rows, positions = new[new_name], kept(root, table, item, required)
        counts[(which, new_name, "rows_read")] += len(rows)
        counts[(which, new_name, "rows_the_old_parser_dropped")] += len(rows) - len(positions)
        compare(counts, which, len(positions), len(was[old_name]), f"{new_name}.kept_count")
        for pos, o in zip(positions, was[old_name]):
            n = rows[pos - 1]
            compare(counts, which, n["transaction_date"], o["transaction_date"], f"{new_name}.transaction_date")
            compare(counts, which, blank(n["transaction_code"]), blank(o["transaction_code"]), f"{new_name}.transaction_code")
            compare(counts, which, number(n["transaction_shares"]), o["transaction_shares"], f"{new_name}.transaction_shares")
            compare(counts, which, number(n["transaction_price_per_share"]), o["transaction_price"], f"{new_name}.transaction_price")
            compare(counts, which, blank(n["transaction_acquired_disposed_code"]), blank(o["acquired_disposed_code"]), f"{new_name}.acquired_disposed_code")
            compare(counts, which, number(n["shares_owned_following_transaction"]), o["shares_owned_after"], f"{new_name}.shares_owned_after")
            compare(counts, which, blank(n["direct_or_indirect_ownership"]), blank(o["ownership_direct_indirect"]), f"{new_name}.direct_or_indirect")
            compare(counts, which, blank(n["nature_of_ownership"]), blank(o["ownership_nature"]), f"{new_name}.nature_of_ownership")
            # The old title carried footnote markers ("<value> [F1]"); the reading keeps the value.
            compare(counts, which, blank(n["security_title"]), blank(MARKER.sub("", o["security_title"])), f"{new_name}.security_title")
            if extra:
                compare(counts, which, number(n["conversion_or_exercise_price"]), o["conversion_or_exercise_price"], f"{new_name}.conversion_price")
                compare(counts, which, n["exercise_date"], o["exercise_date"], f"{new_name}.exercise_date")
                compare(counts, which, n["expiration_date"], o["expiration_date"], f"{new_name}.expiration_date")
                compare(counts, which, blank(n["underlying_security_title"]), blank(MARKER.sub("", o["underlying_security_title"])), f"{new_name}.underlying_title")
                compare(counts, which, number(n["underlying_security_shares"]), o["underlying_security_shares"], f"{new_name}.underlying_shares")


counts = collections.Counter()
for p in sorted(glob.glob(str(BRONZE / "filings/sec/*/*/primary/*.xml"))):
    raw = Path(p).read_bytes()
    if b"<ownershipDocument" not in raw:
        counts[("cohort", "not_an_ownership_document", "skipped")] += 1
        continue
    accession = re.search(r"accession=([\d-]+)", p).group(1)
    run(counts, "cohort", accession, raw, raw, XML, {"accession": accession})
for p in sorted((BRONZE / "filing_artifact").iterdir()):
    raw = p.read_bytes()
    accession = re.search(rb"ACCESSION NUMBER:\s*([\d-]+)", raw).group(1).decode()
    run(counts, "artifact", accession, raw, None, SGML, None)
out = collections.defaultdict(dict)
for (which, name, outcome), n in sorted(counts.items()):
    out[which].setdefault(name, {})[outcome] = n
print(json.dumps(out, indent=1, sort_keys=True))
