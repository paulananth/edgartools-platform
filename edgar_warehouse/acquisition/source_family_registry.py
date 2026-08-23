"""Source Family Registry entries: executable per-family acquisition policy.

Ticket 15 delivers the first entry, ``filing_artifact`` -- fetch and
completeness behavior for one SEC filing document/attachment, reusing the
same byte-preserving content gateway ``bronze_filing_artifacts.py`` already
uses for this exact object class (``filing_content_gateway``, the raw SEC
HTTP path -- filing document/attachment bytes are deliberately *not* routed
through ``edgartools_sec_gateway``, which is reserved for catalog/facts
object classes; see that module's own docstring).

Per the change-propagation spec's Ticket 03 GoF constraints, a policy here
is a narrow first-class object satisfying ``facade.SourceFamilyPolicy`` --
not a class hierarchy, and it never performs authorization, hashing, Bronze
writes, or ledger transitions; those stay in ``facade.py``.
"""

from __future__ import annotations

from dataclasses import dataclass

from edgar_warehouse.acquisition.facade import SourceFamilyPolicy
from edgar_warehouse.infrastructure.filing_content_gateway import (
    download_filing_content_bytes,
)

FILING_ARTIFACT_SOURCE_FAMILY = "filing_artifact"


@dataclass(frozen=True)
class FilingArtifactPolicy:
    """Fetch and completeness behavior for one filing document/attachment.

    Completeness here is deliberately scoped to *this one artifact*: a
    non-empty byte-preserving response. Proving that an accession's full
    configured document set is present is a per-accession concern for a
    later ticket (Ticket 19's Silver acceptance seam), not this Strategy.
    """

    identity: str

    def fetch(self, source_url: str) -> bytes:
        return download_filing_content_bytes(source_url, self.identity)

    def is_complete(self, payload: bytes) -> bool:
        return bool(payload)


def build_source_family_registry(*, identity: str) -> dict[str, SourceFamilyPolicy]:
    """Return the Source Family Registry entries this deployment supports."""

    return {
        FILING_ARTIFACT_SOURCE_FAMILY: FilingArtifactPolicy(identity=identity),
    }
