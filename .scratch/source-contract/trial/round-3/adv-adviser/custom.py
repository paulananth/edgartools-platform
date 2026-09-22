# Custom Steps for iapd.adv_adviser. Standard library only (no `requires`).
from datetime import datetime

from source_contract import Reject, value_step


@value_step("adv_submitted_date", version=1)
def adv_submitted_date(raw: str) -> str:
    """IAPD writes DateSubmitted as 'MM/DD/YYYY hh:mm:ss AM'. Return the ISO date 'YYYY-MM-DD'.

    No primitive reads a US-ordered date (date_prefix needs a leading YYYY-MM-DD, timestamp
    needs ISO 8601). The time of day is dropped on purpose: IAPD does not say its time zone.
    """
    try:
        return datetime.strptime(raw.strip(), "%m/%d/%Y %I:%M:%S %p").date().isoformat()
    except (AttributeError, ValueError):
        raise Reject(f"DateSubmitted is not MM/DD/YYYY hh:mm:ss AM|PM: {raw!r}")
