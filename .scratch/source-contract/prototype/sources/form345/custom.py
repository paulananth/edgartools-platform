"""PROTOTYPE — Form 3/4/5 custom steps (ticket 04 Q4: value steps, pure, versioned).

Both steps exist because edgartools' company-or-person classifier cannot be
written as primitives (research 02, A.4). The logic mirrors
edgar_warehouse/parsers/ownership.py:_is_company, copied rather than imported
so this folder stays self-contained (check 1).
"""

from edgar.display.formatting import reverse_name
from edgar.entity.constants import _classify_is_individual

from source_engine import check_step, value_step


def _is_company(cik, payload):
    if not payload:
        return False
    forms = list((payload.get("filings") or {}).get("recent", {}).get("form") or [])[:50]
    return not _classify_is_individual(
        name=payload.get("name"),
        tickers=payload.get("tickers"),
        exchanges=payload.get("exchanges"),
        state_of_incorporation=payload.get("stateOfIncorporation"),
        entity_type=payload.get("entityType"),
        forms=forms,
        ein=payload.get("ein"),
        cik=cik,
        insider_transaction_for_issuer_exists=bool(payload.get("insiderTransactionForIssuerExists")),
        insider_transaction_for_owner_exists=bool(payload.get("insiderTransactionForOwnerExists")),
    )


@value_step("owner_display_name", version=1)
def owner_display_name(raw: str, cik, submissions: dict) -> str:
    """The registry name as-is for a company, reversed for a person ("COOK TIMOTHY D" → "Timothy D Cook")."""
    return raw if _is_company(cik, submissions.get("payload")) else reverse_name(raw)


@value_step("owner_kind", version=1)
def owner_kind(cik, submissions: dict) -> str:
    """Provisional identity kind for the adapter. NOT rule C-J — see prototype findings."""
    return "company" if _is_company(cik, submissions.get("payload")) else "person"


@check_step("owner_name_has_letters", version=1)
def owner_name_has_letters(owner_name_raw: str):
    return None if any(ch.isalpha() for ch in owner_name_raw or "") else f"owner name {owner_name_raw!r} has no letters"
