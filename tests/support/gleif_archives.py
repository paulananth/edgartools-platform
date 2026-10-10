"""A one-member GLEIF archive and its pinned metadata, for publication tests."""

import io
import zipfile


def archive_bytes(raw, name="source.json"):
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(name, raw)
    return output.getvalue()


def metadata(count=1, **changes):
    return {
        "format": "json.zip",
        "cdf_version": "LEI_3.1",
        "content_date": "2026-09-11T16:00:00+00:00",
        "file_content": "GLEIF_FULL_PUBLISHED",
        "delta_start": None,
        "record_count": count,
        **changes,
    }
