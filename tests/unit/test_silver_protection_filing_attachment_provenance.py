"""Regression: sec_filing_attachment's document_url must not block publication.

Root cause (2026-08-06): a multi-registrant filing (e.g. a DEFA14A jointly
associated with several CIKs) produces a different, but equally correct,
document_url per CIK that discovers it -- edgar.Attachment.url embeds the
querying CIK's own path segment, and SEC serves a distinct SGML header (and
therefore filing_metadata["CIK"]) depending on which associated CIK's
directory the submission is fetched through. Confirmed live: fetching the
same document via edgar.Company(cik) for 4 different CIKs associated with
accession 0001137439-25-001001 returned 4 different document_url values,
while every other attachment field (sequence_number, document_type,
description, is_primary) and the real content-identity signal
(raw_object_id) were identical. Before this fix, any two candidates that
discovered the same accession/document under different CIKs produced an
unresolvable SemanticMergeConflictError and blocked publication entirely.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from edgar_warehouse.silver_protection import merge_candidate_into_canonical
from edgar_warehouse.silver_store import SilverDatabase


def _insert_attachment(db: SilverDatabase, *, document_url: str) -> None:
    db._conn.execute(
        """
        INSERT INTO sec_filing_attachment
            (accession_number, sequence_number, document_name, document_type,
             document_description, document_url, is_primary, raw_object_id)
        VALUES
            ('0001137439-25-001001', '1', 'mac08052025defa14a.htm', 'DEFA14A',
             '', ?, TRUE, 'deadbeef')
        """,
        [document_url],
    )


def test_cross_cik_document_url_difference_does_not_block_publication(tmp_path: Path) -> None:
    canonical_path = tmp_path / "canonical.duckdb"
    canonical_db = SilverDatabase(str(canonical_path))
    _insert_attachment(
        canonical_db,
        document_url="https://www.sec.gov/Archives/edgar/data/27574/000113743925001001/mac08052025defa14a.htm",
    )
    canonical_db.close()

    candidate_path = tmp_path / "candidate.duckdb"
    candidate_db = SilverDatabase(str(candidate_path))
    _insert_attachment(
        candidate_db,
        document_url="https://www.sec.gov/Archives/edgar/data/230173/000113743925001001/mac08052025defa14a.htm",
    )
    candidate_db.close()

    output_path = tmp_path / "merged.duckdb"
    result = merge_candidate_into_canonical(candidate_path, canonical_path, output_path)

    assert "sec_filing_attachment" in result.tables_merged

    import duckdb

    conn = duckdb.connect(str(output_path))
    try:
        row = conn.execute(
            "SELECT document_url FROM sec_filing_attachment "
            "WHERE accession_number = '0001137439-25-001001' "
            "AND document_name = 'mac08052025defa14a.htm'"
        ).fetchone()
    finally:
        conn.close()

    # Canonical's first-observed URL stays authoritative -- same precedent
    # already established for raw_object_id on this table.
    assert row[0] == (
        "https://www.sec.gov/Archives/edgar/data/27574/000113743925001001/mac08052025defa14a.htm"
    )


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
