"""Reload the RDM database from the published code sets (ticket 189).

`rules/reference/published/<set>/<version>/` keeps a version's codes, labels and crosswalk (canonical.jsonl)
and its sha256 (pin.json), but not the code set's own words or where its codes came from. Those are in
WORDS below, each taken from the draft that first made the set (its ticket or draft script), and in
skills/data-operations/SKILL.md ("RDM code sets and their sources").

For each version, in order: draft it from its canonical rows, approve it, publish it into a temporary
folder, and refuse unless the published bytes equal the repository's file and its pin. Nothing is written
into the repository. A version RDM already holds is left alone.

    uv run python scripts/dev/reload_rdm.py            # uses RDM_DATABASE_URL, never printed

A new version of a published code set is drafted from its newest published rows plus the added codes
(each a row in the published shape: code, label, definition, parent_code, level, properties), for
`edgar-warehouse rdm draft --file`; a code already held is refused. Reload first, so the version it
supersedes is in RDM for `rdm diff`:

    uv run python scripts/dev/reload_rdm.py next <code set> <version> --add <codes.yaml> --out <draft.yaml>
"""
from __future__ import annotations

import hashlib
import json
import sys
import tempfile
from datetime import date
from pathlib import Path

from edgar_warehouse.control_contract import Blocked
from edgar_warehouse.database_connections import engine_from_env
from edgar_warehouse.rdm.store import RDM

ROOT = Path(__file__).resolve().parents[2]
PUBLISHED = ROOT / "rules" / "reference" / "published"
RELOAD = "load rdm use skills (operator, 2026-11-03, ticket 189)"

# Per code set: the words that never change, and per version who made it, from what, and the words
# the operator first approved it with (None where the ticket records "approved" without them).
WORDS = {
    "sec-place-types": dict(
        name="EDGAR place types",
        definition="The four kinds of place an EDGAR state or country code can be, which a place code "
                   "crosswalks to as a broad match.",
        authority="SEC EDGAR state and country codes", ticket="profiling 02",
        versions={"1": ("claude/data-profiling (profiling ticket 02)",
                        "Ticket 02's last step needs your approval. Approved")}),
    "sec-place-codes": dict(
        name="EDGAR state and country codes",
        definition="The codes a filer writes for its state or country of incorporation and of each address",
        authority="SEC EDGAR state and country codes, as the SEC's submissions carry them", ticket="profiling 02",
        usage=[("mdm", "company", "state_of_incorporation", "upper_trimmed"),
               ("source", "sec.submissions.company", "stateOfIncorporation", "exact"),
               ("source", "sec.submissions.company", "addresses.stateOrCountry", "exact"),
               ("source", "sec.submissions.company", "addresses.countryCode", "exact")],
        hints=[("meaning", "A US state or territory reads as its postal code; X1 is the United States with no state; XX is unknown"),
               ("use_when", "Turning a filer's state or country code into an ISO 3166 jurisdiction (the iso-3166 crosswalk)"),
               ("avoid_when", "Judging a place by its label alone: labels are SEC's own spellings")],
        versions={"1": ("claude/data-profiling (profiling ticket 02)",
                        "Ticket 02's last step needs your approval. Approved")}),
    "sec-ownership-transaction-codes": dict(
        name="Form 4 transaction codes",
        definition="The code an insider writes for the character of each transaction reported on Form 4 "
                   "(Table I column 3, Table II column 4) and Form 5",
        authority="SEC Form 4 General Instruction 8, Transaction Codes (form4.pdf, sha256 275cfc91..., read 2026-10-13)",
        ticket="profiling 07",
        usage=[("source", "sec.ownership", "transactionCoding.transactionCode", "exact")],
        hints=[("meaning", "One letter for the kind of transaction: P a purchase, S a sale, A an award, M an exercise "
                           "of an exempt derivative, F shares withheld for tax, G a gift, J other (described in a footnote)"),
               ("use_when", "Telling trades (P, S) from awards, exercises and gifts in insider transactions"),
               ("avoid_when", "Reading K alone: the SEC asks for K beside the code that describes the transaction (S/K, P/K)")],
        versions={"1": ("claude/data-onboarding (profiling ticket 07)", None)}),
    "openfigi-country-composite": dict(
        name="OpenFIGI country composite codes",
        definition="The countries whose ISINs OpenFIGI answers with the country's own composite exchange code, "
                   "with the share of found ISINs that carry it.",
        authority="OpenFIGI mapping answers, measured on the local OpenFIGI capture", ticket="120",
        versions={"1": ("claude (ticket 120)", "approved in the operator's words (ticket 120)")}),
    "iso-10383-mic": dict(
        name="ISO 10383 market identifier codes",
        definition="Every active ISO 10383 market identifier code: operating MICs and the segments under them, "
                   "with ISO's market name; OpenFIGI's exchange code is a crosswalk where OpenFIGI gave one.",
        authority="ISO 10383 market identifier codes (ISO capture), with OpenFIGI's own exchange-code answers",
        ticket="138",
        versions={"1": ("claude (ticket 138)", "the operator's rulings of 2026-10-26, recorded under the standing "
                                                "rule \"auto merge and not ask for approval\"")}),
    "nport-filed-currencies": dict(
        name="Currency codes N-PORT holdings file",
        definition="The three-letter currency codes the N-PORT holdings of the 2026 Q2 data set file, "
                   "with ISO 4217's names as labels.",
        authority="SEC Form N-PORT data set 2026 Q2 (codes); ISO 4217 (names)", ticket="138",
        versions={"1": ("claude (ticket 138 part B3)", "N-PORT's filed codes (Recommended)")}),
    "sec-sic-codes": dict(
        name="SEC SIC codes",
        definition="The Standard Industrial Classification codes the SEC's company submissions carry, each with "
                   "its one description; 0000 is kept invalid: no SIC code assigned.",
        authority="SEC company submissions (captured), SEC's SIC code descriptions", ticket="129",
        versions={"1": ("claude (ticket 129)", "Approve version 1 (Recommended)")}),
    "financial-line-items": dict(
        name="Financial line items",
        definition="The standard line items silver keeps for each company and annual period, each chosen from the "
                   "concepts a filer reports, in the order the line-item map gives.",
        authority="internal", ticket="46",
        usage=[("silver", "company_line_item", "line_item", "exact")],
        hints=[("meaning", "A code's property `period`: duration (a flow over the year) or instant (a balance at its end)."),
               ("use_when", "Naming a standard financial figure of a company and year; its crosswalk names the "
                            "reported concepts it can come from.")],
        versions={"1": ("claude (ticket 46)", "Yes, code set + crosswalk (Recommended)")}),
    "corporate-tax-rates": dict(
        name="Statutory corporate income tax rates",
        definition="Each jurisdiction's combined central and sub-central statutory corporate income tax rate for "
                   "each year, as the OECD publishes it, in percent of taxable income.",
        authority="OECD Corporate Tax Statistics (dataflow OECD.CTP.TPS, DSD_TAX_CIT@DF_CIT 2.0)", ticket="133",
        usage=[("other", "company measures", "ROIC tax rate", "exact")],
        hints=[("meaning", "A statutory corporate income tax rate: central plus sub-central, before incentives"),
               ("use_when", "ROIC needs a tax rate and the filer's effective rate is not meaningful (pretax income "
                            "zero or negative, or the rate outside 0 to 100 percent)"),
               ("avoid_when", "A filer's own effective rate is meaningful; use that instead")],
        versions={"1": ("Claude (company-financials, ticket 133)", None)}),
    "mdm-relationship-types": dict(
        name="MDM relationship types",
        definition="The relationship types MDM masters, each with the rules it runs by; its capacities are its child codes.",
        authority="internal", ticket="132",
        usage=[("mdm", "relationship", "type", "exact")],
        hints=[("meaning", "A type's properties: from and to (the kinds at each end), from_profile and to_profile, "
                           "hierarchy, cycles, one_parent, one_target, ultimate_parent and ultimate_type, keeps_start, ends_parent_links.")],
        versions={"1": ("claude (ticket 132)", "Use RDM for keeping types and other information; "
                                               "Add code properties to RDM (Recommended)"),
                  "2": ("claude (ticket 182)", None),
                  "3": ("claude (ticket 24)", "This can't be true \"Security with two issuers keep two ISSUED_BY links\" "
                                              "fix the root cause"),
                  "4": ("claude (Form ADV related persons)", "RELATED_PERSON (Recommended)"),
                  "5": ("claude (ticket 234, N-CEN adviser types)",
                        "Question: should the two capacities of INVESTMENT_ADVISER_TO be named with N-CEN's own "
                        "terms, advisor and subadvisor, labelled \"Advisor\" and \"Subadvisor\" as the data set "
                        "writes them? yes but any type must also be added to rdm maybe this should be in data "
                        "modeling skill")}),
    "mdm-relationship-types-before-real-names": dict(
        name="MDM relationship types before the real names",
        definition="The table of relationship types as the operator approved it before the types took their real "
                   "names; the test layer that rebuilds that approval reads it.",
        authority="internal", ticket="188",
        versions={"1": ("claude (ticket 188)", None)}),
}
# Crosswalk targets must be held before the set that points at them.
ORDER = ["sec-place-types", "sec-place-codes", "sec-ownership-transaction-codes", "openfigi-country-composite",
         "iso-10383-mic", "nport-filed-currencies", "sec-sic-codes", "financial-line-items", "corporate-tax-rates",
         "mdm-relationship-types", "mdm-relationship-types-before-real-names"]
CODE_KEYS = ("code", "label", "definition", "parent_code", "valid_from", "valid_to", "status", "invalid_reason",
             "value", "unit", "properties")


def draft_of(code_set: str, version: str, rows: list[dict], supersedes: str | None) -> dict:
    parents = {r["code"]: r["parent_code"] for r in rows}

    def depth(code):
        return 1 if parents[code] is None else 1 + depth(parents[code])

    levels = sorted({(depth(r["code"]), r["level"]) for r in rows if r.get("level")})
    codes = []
    for r in rows:
        code = {k: r[k] for k in CODE_KEYS if k in r}
        for k in ("valid_from", "valid_to"):
            if isinstance(code.get(k), str):
                code[k] = date.fromisoformat(code[k])
        codes.append(code)
    return dict(
        codes=codes,
        levels=[{"depth": d, "name": n} for d, n in levels],
        labels=[{"code": r["code"], "language": lang, "kind": kind, "label": label, "source": "published file"}
                for r in rows for lang, kind, label in r["labels"]],
        crosswalk=[{"from_code": r["code"], "to_set": s, "to_version": v, "to_code": c, "match_type": m}
                   for r in rows for s, v, c, m in r["crosswalk"]])


def next_draft(code_set: str, version: str, added: list[dict]) -> dict:
    """The draft of a new version: the newest published version's rows plus the added codes."""
    previous = max(WORDS[code_set]["versions"], key=int)
    folder = PUBLISHED / code_set / previous
    data = (folder / "canonical.jsonl").read_bytes()
    if hashlib.sha256(data).hexdigest() != json.loads((folder / "pin.json").read_text())["sha256"]:
        raise Blocked(f"{code_set} {previous}: the repository's file is not its pin")
    rows = [json.loads(line) for line in data.decode().splitlines()]
    if refused := sorted({r["code"] for r in added} & {r["code"] for r in rows}):
        raise Blocked(f"already held in {code_set} {previous}: {refused}")
    rows += [{"labels": [["en", "preferred", r["label"]]], "crosswalk": [], "parent_code": None, **r} for r in added]
    words = WORDS[code_set]
    return {"code_set": {"code_set": code_set}, "version": version, "supersedes": previous,
            "created_by": "claude (scripts/dev/reload_rdm.py next)",
            "evidence": {"supersedes": f"rules/reference/published/{code_set}/{previous}",
                         "added": [r["code"] for r in added]},
            "usage": [dict(zip(("store", "object", "field", "match"), u)) for u in words.get("usage", ())],
            "hints": [dict(zip(("kind", "text"), h)) for h in words.get("hints", ())],
            **draft_of(code_set, version, rows, previous)}


def held(rdm: RDM, code_set: str, version: str) -> bool:
    try:
        rdm.version(code_set, version)
    except Blocked:
        return False
    return True


def main() -> int:
    rdm = RDM(engine_from_env("RDM_DATABASE_URL"))
    done = []
    for code_set in ORDER:
        words = WORDS[code_set]
        previous = None
        for version in sorted(words["versions"]):
            folder = PUBLISHED / code_set / version
            data = (folder / "canonical.jsonl").read_bytes()
            pin = json.loads((folder / "pin.json").read_text())["sha256"]
            if hashlib.sha256(data).hexdigest() != pin:
                raise Blocked(f"{code_set} {version}: the repository's file is not its pin")
            if held(rdm, code_set, version):
                previous = version
                continue
            created_by, first_words = words["versions"][version]
            rows = [json.loads(line) for line in data.decode().splitlines()]
            body = draft_of(code_set, version, rows, previous)
            rdm.draft({"code_set": code_set, "name": words["name"], "definition": words["definition"],
                       "authority": words["authority"], "steward": "operator"},
                      version, body.pop("codes"), created_by=created_by, supersedes=previous,
                      evidence={"reloaded_from": f"rules/reference/published/{code_set}/{version}",
                                "sha256": pin, "ticket": words["ticket"], "codes": len(rows),
                                "first_approved": first_words or "recorded in the ticket"},
                      usage=[dict(zip(("store", "object", "field", "match"), u)) for u in words.get("usage", ())],
                      hints=[dict(zip(("kind", "text"), h)) for h in words.get("hints", ())], **body)
            rdm.approve(code_set, version, by="operator", words=RELOAD)
            with tempfile.TemporaryDirectory() as scratch:
                published = rdm.publish(code_set, version, out=Path(scratch))
                again = (Path(scratch) / code_set / version / "canonical.jsonl").read_bytes()
            if again != data or published["sha256"] != pin:
                raise Blocked(f"{code_set} {version} reloaded to other bytes than its pin; stopped")
            done.append((code_set, version, len(rows)))
            previous = version
            print(f"{code_set} {version}: {len(rows)} codes, sha256 equals its pin")
    print(f"{len(done)} versions reloaded")
    return 0


if __name__ == "__main__":
    if sys.argv[1:2] == ["next"]:
        import argparse

        import yaml

        parser = argparse.ArgumentParser(prog="reload_rdm.py next")
        parser.add_argument("code_set")
        parser.add_argument("version")
        parser.add_argument("--add", required=True, type=Path)
        parser.add_argument("--out", required=True, type=Path)
        args = parser.parse_args(sys.argv[2:])
        body = next_draft(args.code_set, args.version, yaml.safe_load(args.add.read_text()) or [])
        args.out.write_text(yaml.safe_dump(body, sort_keys=False, allow_unicode=True), encoding="utf-8")
        print(f"{args.out}: {args.code_set} {args.version} supersedes {body['supersedes']}, {len(body['codes'])} codes")
        sys.exit(0)
    sys.exit(main())
