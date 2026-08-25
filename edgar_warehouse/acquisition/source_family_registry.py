"""Source Family Registry Strategy implementations: per-family acquisition policy.

Ticket 15 delivers the first entry, ``filing_artifact`` -- fetch and
completeness behavior for one SEC filing document/attachment, reusing the
same byte-preserving content gateway ``bronze_filing_artifacts.py`` already
uses for this exact object class (``filing_content_gateway``, the raw SEC
HTTP path -- filing document/attachment bytes are deliberately *not* routed
through ``edgartools_sec_gateway``, which is reserved for catalog/facts
object classes; see that module's own docstring).

Ticket 21 adds the second entry, ``submissions`` -- fetch and completeness
behavior for one SEC submissions main snapshot or pagination file. Both are
catalog objects (submissions.json / a company's paginated filing-history
file), the object class ``edgartools_sec_gateway`` *is* reserved for -- the
inverse gateway choice from ``filing_artifact``, deliberately, per that
module's own docstring boundary. One Strategy class serves both logical-key
kinds (main and pagination): from the Facade's point of view both are "fetch
one URL, get bytes, check it's a well-formed JSON object" -- structurally
identical, differing only in which URL a caller supplies. Proving that a
main snapshot's *referenced pagination files* are all captured (Ticket 21
bullet 2) is a cross-fetch concern the Facade's one-URL-per-call contract
cannot express -- that lives above this module, in the new submissions
discovery driver and its Silver-acceptance module, not inside ``is_complete``.

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
(``FilingArtifactPolicy``, ``SubmissionsPolicy``); it deliberately has no
knowledge of versioning, activation, or which families are currently covered.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass

from edgar_warehouse.infrastructure.edgartools_sec_gateway import (
    download_bytes as download_sec_catalog_bytes,
)
from edgar_warehouse.infrastructure.filing_content_gateway import (
    download_filing_content_bytes,
)

FILING_ARTIFACT_SOURCE_FAMILY = "filing_artifact"
SUBMISSIONS_SOURCE_FAMILY = "submissions"
COMPANY_FACTS_SOURCE_FAMILY = "company_facts"
REFERENCE_CATALOG_SOURCE_FAMILY = "reference_catalog"

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


def _is_valid_json_object(payload: bytes) -> bool:
    if not payload:
        return False
    try:
        document = json.loads(payload)
    except (UnicodeDecodeError, json.JSONDecodeError):
        return False
    return isinstance(document, dict)


# Ticket 21: distinct from filing_artifact's checks -- a submissions payload
# that decodes to non-empty bytes but isn't well-formed JSON (a truncated
# download, an SEC error page served with a 200) must not be treated as
# complete, since silver_store.py's staging loaders would fail or silently
# produce nothing useful from it downstream.
_SUBMISSIONS_COMPLETENESS_CHECKS: dict[str, Callable[[bytes], bool]] = {
    "valid_json_object": _is_valid_json_object,
}


@dataclass(frozen=True)
class SubmissionsPolicy:
    """Fetch and completeness behavior for one submissions main snapshot or
    pagination file -- one Strategy serves both logical-key kinds (see this
    module's own docstring for why).
    """

    identity: str
    completeness_policy: str = "valid_json_object"

    def fetch(self, source_url: str) -> bytes:
        return download_sec_catalog_bytes(source_url, self.identity)

    def is_complete(self, payload: bytes) -> bool:
        check = _SUBMISSIONS_COMPLETENESS_CHECKS.get(self.completeness_policy)
        if check is None:
            raise UnsupportedCompletenessPolicy(
                f"completeness_policy={self.completeness_policy!r} has no "
                "installed check for submissions"
            )
        return check(payload)


# Ticket 22: same shape as _SUBMISSIONS_COMPLETENESS_CHECKS, reusing the
# shared _is_valid_json_object check -- a company-facts payload with an
# empty `"facts": {}` section is still a valid, complete snapshot (a real
# CIK can have zero XBRL facts), so completeness here is deliberately just
# "well-formed JSON object", not "non-empty facts section".
_COMPANY_FACTS_COMPLETENESS_CHECKS: dict[str, Callable[[bytes], bool]] = {
    "valid_json_object": _is_valid_json_object,
}


@dataclass(frozen=True)
class CompanyFactsPolicy:
    """Fetch and completeness behavior for one company's XBRL company-facts
    snapshot (SEC's ``/api/xbrl/companyfacts/CIK{cik:010}.json`` endpoint).

    A catalog/facts object class, same as ``submissions`` -- uses the same
    edgartools-backed gateway.
    """

    identity: str
    completeness_policy: str = "valid_json_object"

    def fetch(self, source_url: str) -> bytes:
        return download_sec_catalog_bytes(source_url, self.identity)

    def is_complete(self, payload: bytes) -> bool:
        check = _COMPANY_FACTS_COMPLETENESS_CHECKS.get(self.completeness_policy)
        if check is None:
            raise UnsupportedCompletenessPolicy(
                f"completeness_policy={self.completeness_policy!r} has no "
                "installed check for company_facts"
            )
        return check(payload)


def _is_valid_ticker_catalog_json(payload: bytes) -> bool:
    """Ticket 23: stricter than ``_is_valid_json_object`` -- a ticker catalog
    payload that decodes to *some* well-formed JSON object but not one of SEC's
    two actual company-tickers shapes (``company_tickers.json``'s numbered-dict
    shape, or ``company_tickers_exchange.json``'s ``{"fields": [...], "data":
    [...]}`` shape) must not be treated as complete -- ``_parse_company_ticker_rows``
    silently returns an empty list for any payload shape it doesn't recognize,
    which would otherwise be indistinguishable from a genuine, valid zero-member
    catalog (bullet 2's complete-empty-scope case). An empty ``{}`` or an empty
    ``data`` list is still complete -- SEC serving a real empty catalog is a
    legitimate, if unlikely, outcome, not a malformed one.
    """

    if not payload:
        return False
    try:
        document = json.loads(payload)
    except (UnicodeDecodeError, json.JSONDecodeError):
        return False
    if not isinstance(document, dict):
        return False
    fields = document.get("fields")
    data = document.get("data")
    if isinstance(fields, list) and isinstance(data, list):
        return True
    if not document:
        return True
    return all(isinstance(entry, dict) and "cik_str" in entry for entry in document.values())


_REFERENCE_CATALOG_COMPLETENESS_CHECKS: dict[str, Callable[[bytes], bool]] = {
    "valid_ticker_catalog_json": _is_valid_ticker_catalog_json,
}


@dataclass(frozen=True)
class ReferenceCatalogPolicy:
    """Fetch and completeness behavior for one SEC reference catalog snapshot
    (``company_tickers.json`` or ``company_tickers_exchange.json``).

    A catalog/facts object class, same gateway as ``submissions``/
    ``company_facts``. Scoped to the two auto-refetched ticker catalogs only
    -- the PCAOB firm registry is a supported reference source too
    (``edgartools_sec_gateway``'s catalog list), but it arrives today only via
    the operator-driven evidence-import ladder
    (``warehouse_orchestrator.py``'s ``pcaob_firm_registry`` relationship-source
    kind), not an auto-refetched snapshot -- Ticket 25 owns that path, not
    this one.
    """

    identity: str
    completeness_policy: str = "valid_ticker_catalog_json"

    def fetch(self, source_url: str) -> bytes:
        return download_sec_catalog_bytes(source_url, self.identity)

    def is_complete(self, payload: bytes) -> bool:
        check = _REFERENCE_CATALOG_COMPLETENESS_CHECKS.get(self.completeness_policy)
        if check is None:
            raise UnsupportedCompletenessPolicy(
                f"completeness_policy={self.completeness_policy!r} has no "
                "installed check for reference_catalog"
            )
        return check(payload)
