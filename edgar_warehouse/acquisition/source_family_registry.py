"""Source Family Registry Strategy implementations: per-family acquisition policy.

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

Ticket 20 retired this module's own ``build_source_family_registry`` (an
unconditional, unversioned in-memory dict every process constructed fresh)
in favor of ``registry_ledger.build_active_source_family_registry`` -- the
*only* sanctioned way a caller may obtain a real ``SourceFamilyPolicy`` now,
gated on a Source Family Registry version having actually activated. This
module keeps only the Strategy implementations themselves
(``FilingArtifactPolicy``); it deliberately has no knowledge of versioning,
activation, or which families are currently covered.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from edgar_warehouse.infrastructure.filing_content_gateway import (
    download_filing_content_bytes,
)

FILING_ARTIFACT_SOURCE_FAMILY = "filing_artifact"

# Ticket 32: the registry's completeness_policy field names which of these
# checks applies -- validated, not merely read, so a coverage row declaring
# a policy nothing here implements fails closed at fetch time rather than
# silently falling back to some default.
_COMPLETENESS_CHECKS: dict[str, Callable[[bytes], bool]] = {
    "non_empty_payload": bool,
}


class UnsupportedCompletenessPolicy(RuntimeError):
    """A covered family declares a completeness_policy this Strategy cannot check."""


@dataclass(frozen=True)
class FilingArtifactPolicy:
    """Fetch and completeness behavior for one filing document/attachment.

    Completeness here is deliberately scoped to *this one artifact*: a
    non-empty byte-preserving response. Proving that an accession's full
    configured document set is present is a per-accession concern for a
    later ticket (Ticket 19's Silver acceptance seam), not this Strategy.
    """

    identity: str
    completeness_policy: str = "non_empty_payload"

    def fetch(self, source_url: str) -> bytes:
        return download_filing_content_bytes(source_url, self.identity)

    def is_complete(self, payload: bytes) -> bool:
        check = _COMPLETENESS_CHECKS.get(self.completeness_policy)
        if check is None:
            raise UnsupportedCompletenessPolicy(
                f"completeness_policy={self.completeness_policy!r} has no "
                "installed check for filing_artifact"
            )
        return check(payload)
