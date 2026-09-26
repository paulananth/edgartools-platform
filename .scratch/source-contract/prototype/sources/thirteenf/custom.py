"""The same blanking parse_thirteenf applies to text: empty, 'none', and 'nan' are null."""

from source_engine import value_step


@value_step("blank_missing_token", version=1)
def blank_missing_token(value) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text or text.lower() in ("nan", "none"):
        return None
    return text
