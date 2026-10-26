"""Qualified storage protocols retain their fixed migration fingerprints."""
import json
from pathlib import Path
from types import SimpleNamespace

from sqlalchemy.dialects import mssql, mysql, postgresql


def test_frozen_protocol_fingerprints(storage_api):
    expected = json.loads(Path(__file__).with_name("expected_protocol_fingerprints.json").read_text())
    found = {}
    for name, module in (("postgresql",postgresql),("mysql",mysql),("mssql",mssql)):
        dialect = module.dialect()
        for protocol in range(1,4 if name == "mssql" else 7):
            metadata, tables = storage_api.model("skill_merge","invented",protocol=protocol)
            adapter = SimpleNamespace(engine=SimpleNamespace(dialect=dialect),metadata=metadata,
                protocol=protocol,routines=storage_api.capabilities(dialect,tables,"skill_merge",protocol=protocol),
                commit_guards=storage_api.commit_guards(dialect,tables,"skill_merge"),
                migration_guards=storage_api.migration_guards(dialect,tables,"skill_merge") if protocol >= 2 else [])
            found[name+str(protocol)] = sorted(storage_api._migration_checksums(adapter))
    assert found == expected
