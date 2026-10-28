# 144: Python libraries the code imports

Priority: 144. Map: [Rebuild priorities](../map.md). Opened 2026-10-28 08:55 ET.

Type: task. Status: open (PR pending).
Raised by the operator, 2026-10-28: "Cleanup Python libraries now that we are
using rust for most work"; on edgartools: "Remove it entirely".

## Found (2026-10-28, every import in `edgar_warehouse`, `tests`, `infra/scripts`, `scripts`, `skills`)

The platform imports pyarrow, pytz, httpx, PyYAML, boto3, SQLAlchemy, psycopg2
and openpyxl (database drivers also load by connection URL). Nothing imports:
edgartools, spaCy and its English model, click, zstandard, fsspec, s3fs,
fastapi, uvicorn, sqladmin, jellyfish, splink, pydantic, the Snowflake
connector (only the two dashboards, which install from their own
`requirements.txt` and `environment.yml`), the `dashboard` extra (streamlit,
plotly, pandas) or the `market` extra (yfinance, fredapi). ijson and lxml are
imported only by two qualification scripts and one fixture builder; the Rust
engine reads JSON and XML. duckdb (through splink) and pandas (through
edgartools) reached the tests indirectly.

## Parts

- [x] Inventory of every import, counting indented ones (2026-10-28 08:55 ET): above
- [x] Operator's decision on edgartools (2026-10-28): "Remove it entirely"
- [x] `pyproject.toml` declares only what the code imports; `dashboard` and
  `market` extras removed; duckdb and pandas in the `dev` group for the
  tests (2026-10-28 08:55 ET): the lock goes from 154 packages to 50 (52 with the parity tests' decoders), the
  environment from 540 MB to 323 MB
- [x] `scripts/batch/` (edgartools smoke tests) deleted; `test_sec_place_codes.py`
  states SEC's 309 codes and their digest itself, checked equal to the list
  edgartools shipped before it was removed, and seen to fail on a wrong count
  (2026-10-28 08:55 ET)
- [x] CLAUDE.md, AGENTS.md and `docs/project-overview.md` no longer call
  edgartools a dependency (2026-10-28 08:55 ET)
- [x] Verified (2026-10-28 08:55 ET): all 149 platform modules import; unit,
  architecture and engine tests 1,146 passed; MDM tests 1,128 passed
- [x] CI's Engine job found the archive parity tests import ijson and lxml as the
  independent decoders they compare the Rust engine with (2026-10-28 09:03 ET): both
  join the `dev` group (test-only); the lock holds 52 packages; the parity tests 16
  passed, the engine tests 1,021 passed locally before
- [ ] PR, CI green, merge
- [ ] The dependency images rebuild on their next publish (the lock hash
  changes); nothing to do before then
- [x] Learning → skill (2026-10-28 08:55 ET): CLAUDE.md "Python libraries":
  declare only what the code imports; test-only libraries go in `dev`; find
  the import before adding a library
