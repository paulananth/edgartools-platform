# Publication verification fixture v1

Synthetic source-only fixture with the accepted Golden Copy family shape:
Level 1, relationships and reporting exceptions verified together. These JSONL
files are not GLEIF XML, downloaded GLEIF records, valid production LEIs, or
independent Company matching truth. No network request is required.

`manifest.json` pins exact member byte counts and SHA256 values. Under the fixture
interpretation, raw, canonical-source and domain-content hashes all identify the
unchanged JSONL bytes. `dataset.json` pins that interpretation and continuity
contract. `expected.json` pins the source inventory digest and normalized Level 1
assertions and their digest. Integration tests capture the files through real acquisition APIs,
materialize immutable revisions, and verify bytes using restricted PostgreSQL 16
roles. The manifest declares logical keys rather than generated acquisition UUIDs.

Only the Level 1 fixture is normalized into in-memory Company assertions to check
order-independent content hashes. Relationship/exception bytes remain source
evidence. The source-only test publishes **zero domain records**. Separate tests
exercise checkpoint proof retention and rollback without creating an identity.

Run:

```bash
uv run --frozen --extra s3 --extra mdm-runtime --extra mdm pytest \
  tests/integration/test_clean_source_publications.py \
  tests/mdm/test_clean_publication_continuity.py -q
```

Docker and the `postgres:16-alpine` image are required; missing prerequisites fail
instead of skip. The disposable databases are separate from the user's local MDM.
