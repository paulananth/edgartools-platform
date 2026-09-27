"""Insert hand-written comments between keys of the files.dumps output, then write the rules file."""

import sys

src, dst = sys.argv[1], sys.argv[2]
lines = open(src).read().splitlines()

HEADER = [
    "# GLEIF Golden Copy: the MDM mapping of GLEIF's three full files (Level 1 LEI-CDF 3.1,",
    "# relationships RR-CDF 2.1, reporting exceptions REPEX 2.1), read by the native reader",
    "# `edgar_warehouse/mdm/clean/gleif_source.py`. The reader fixes the folder name (`gleif`),",
    "# `native_member`, and `schema_version` = `adapter.version` = gleif-native-record-v1.",
    "# One contract per file (operator, 2026-09-27). The publication-level contract (the three",
    "# member codes and the approved Company LEI scope) has no place in rules/ yet: it lives in",
    "# the registered dataset's `native_contract`.",
]

# (section code or None, stripped line start, comment lines at that line's indent)
NOTES = [
    (None, "family: gleif", ["One capture family for all three files, named like the rules folder (operator, 2026-09-27)."]),
    ("gleif.level1.v1", "nonblocking_deferred_reasons:", [
        "Expected, explained exclusions only (operator, 2026-09-27): outside the approved Company",
        "scope; a kind MDM does not take yet (identity kind, and a relationship type left unmapped);",
        "a valid reporting exception. The same list on all three contracts. Every defect blocks,",
        "including an LEI that fails its check digit (256 L1, 1 RR, 99 REPEX in 2026-09-11).",
    ]),
    ("gleif.level1.v1", "publication_families:", ["The reader accepts only the Golden Copy family (`validate_release`)."]),
    ("gleif.level1.v1", "kind_field:", [
        "Only GENERAL is a Company (`matching.py`); the other categories wait with their Probable",
        "Kind (policy-language.md). SOLE_PROPRIETOR is left unnamed: Person is not settled.",
    ]),
    ("gleif.level1.v1", "identifiers:", [
        "Only the LEI. GLEIF's other ids (validation authority, CIF, SIREN, fund numbers, successor",
        "LEIs) are left out this round; lookup-only identifiers are an open question (operator,",
        "2026-09-27).",
    ]),
    ("gleif.level1.v1", "address:", [
        "GLEIF's legal address, one structured value in the one address field, SEC first (operator,",
        "2026-09-24). AddressNumber, AddressNumberWithinBuilding and MailRouting have no component.",
    ]),
    ("gleif.level1.v1", "gleif_legal_form:", [
        "The ELF code as written; 8888 means 'no ELF code' and cannot be made unknown yet. No field",
        "for the free-text OtherLegalForm (operator, 2026-09-27).",
    ]),
    ("gleif.level1.v1", "gleif_last_update:", ["The raw text: the Name Census compares this exact string (`matching.py`)."]),
    ("gleif.level1.v1", "gleif_registration_authority:", [
        "The registration-authority code and entity id stay fields, not identifiers (operator,",
        "2026-09-27). Under RA000665 (SEC EDGAR) the id is a CIK, a series id or a file number.",
    ]),
    ("gleif.level1.v1", "provenance:", ["The reader keeps the whole native record under `_native`; file hashes travel as occurrences."]),
    ("gleif.level1.v1", "matching:", ["What the SEC-to-GLEIF postcode rule compares: headquarters, kept out of the fields."]),
    ("gleif.relationships.v1", "record_key:", [
        "Paths run over the reader's reshaped row (start, end, relationship_type, valid_from,",
        "valid_to, status, registration_status, _native), not the raw file. The three together are",
        "unique over the 2026-09-11 file (487,721 records).",
    ]),
    ("gleif.relationships.v1", "kind: company", [
        "The reader admits a pair only when both LEIs are in the approved Company scope. A company",
        "record from this code fails its batch until company.yaml lists the code in",
        "defaults.sources: a merge-rule change awaiting its own approval (operator, 2026-09-27).",
        "No `lei` identifier on the start node yet: an open design question (operator, 2026-09-27).",
    ]),
    ("gleif.relationships.v1", "type_values:", [
        "Only accounting consolidation (operator, 2026-09-27). IS_INTERNATIONAL_BRANCH_OF and the",
        "fund links (IS_FUND-MANAGED_BY, IS_SUBFUND_OF, IS_FEEDER_TO) stay captured evidence:",
        "Fund and Branch wait.",
    ]),
    ("gleif.relationships.v1", "properties:", ["GLEIF's own statuses; the text NULL occurs and blocks in the reader."]),
    ("gleif.reporting_exceptions.v1", "kind: company", [
        "Inert today: the reader sets every valid exception aside as reported_parent_exception",
        "(retained evidence, never a parent edge) and never maps it.",
    ]),
]

out = list(HEADER)
section = None
done = set()
for line in lines:
    stripped = line.strip()
    if line.startswith("  gleif.") and stripped.endswith(":"):
        section = stripped[:-1]
    indent = line[: len(line) - len(line.lstrip())]
    for i, (sec, start, comment) in enumerate(NOTES):
        if i in done:
            continue
        if (sec is None or sec == section) and stripped.startswith(start):
            out.extend(indent + "# " + c for c in comment)
            done.add(i)
    out.append(line)
missing = [NOTES[i][:2] for i in range(len(NOTES)) if i not in done]
if missing:
    raise SystemExit(f"anchors not found: {missing}")
open(dst, "w").write("\n".join(out) + "\n")
print("wrote", dst)
