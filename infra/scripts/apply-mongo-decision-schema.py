"""Apply Mongo Decision Projection $jsonSchema. Operator-only; no CI."""

from __future__ import annotations

import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


def _load_dotenv(path: Path) -> None:
    if not path.is_file():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        if key and key not in os.environ:
            os.environ[key] = value


def main() -> int:
    sys.path.insert(0, str(REPO_ROOT))
    _load_dotenv(Path(os.environ.get("ENV_FILE", REPO_ROOT / ".env")))
    uri = os.environ.get("MONGO_PUBLISHER_URI", "").strip()
    if not uri:
        print("MONGO_PUBLISHER_URI is missing. Run provision-atlas-decision-projection.sh", file=sys.stderr)
        return 1
    from edgar_warehouse.serving.mongo_decision_schema import apply_decision_projection_schema
    from edgar_warehouse.serving.mongo_decision_store import mongo_client_from_uri

    client = mongo_client_from_uri(uri)
    apply_decision_projection_schema(client)
    print("applied edgartools_decision collections, $jsonSchema, generation index")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
