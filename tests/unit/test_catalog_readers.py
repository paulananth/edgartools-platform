"""Regression cases for private, repeatable catalog-reader setup."""

import importlib.util
from pathlib import Path
from unittest.mock import Mock

import pytest


EXPOSURE_FILE = Path(__file__).parents[2] / "rules" / "exposure.yaml"


@pytest.fixture
def readers():
    path = Path(__file__).parents[2] / "skills/auto-ontology/scripts/catalog-readers.py"
    spec = importlib.util.spec_from_file_location("catalog_readers_test", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_private_env_roundtrips_shell_escaped_url_and_replaces_duplicates(
    readers, tmp_path
):
    path = tmp_path / "reader.env"
    path.write_text("KEEP=value\nMDM_DATABASE_URL=old\nMDM_DATABASE_URL=duplicate\n")
    value = "postgresql://reader:unusual$pass&word@localhost/database?sslmode=require"
    readers.save_env(path, {"MDM_DATABASE_URL": value})
    loaded = readers.load_env(path)
    assert loaded["MDM_DATABASE_URL"] == value
    assert loaded["KEEP"] == "value"
    assert path.read_text().count("MDM_DATABASE_URL=") == 1
    assert path.stat().st_mode & 0o777 == 0o600


def test_missing_env_does_not_fall_back_to_inherited_credentials(readers, tmp_path):
    with pytest.raises(readers.subprocess.CalledProcessError):
        readers.load_env(tmp_path / "missing.env")


def test_existing_verified_reader_is_reused_without_owner_connection(
    readers, monkeypatch, tmp_path
):
    path = tmp_path / "reader.env"
    url = "postgresql://reader:invented@localhost/catalog?sslmode=require"
    readers.save_env(path, {"STORE_DATABASE_URL": url})
    monkeypatch.setattr(readers, "verify", lambda value, expected=None: {"writable_relations": 0})
    connect = Mock(side_effect=AssertionError("must reuse the qualified reader"))
    monkeypatch.setattr(readers.psycopg, "connect", connect)
    source = {
        "variable": "STORE_DATABASE_URL",
        "store": "rdm",
        "role": "reader",
    }
    actual, report = readers.provision(
        source, {"DB_URL": url}, path, exposure=EXPOSURE_FILE
    )
    assert actual == url
    assert report == {"writable_relations": 0}
    connect.assert_not_called()


def test_failed_embedding_probe_keeps_private_configuration_unchanged(
    readers, monkeypatch, tmp_path
):
    path = tmp_path / "auto.env"
    readers.save_env(
        path,
        {
            "DEFAULT_MODELS_API_KEY": "invented-default",
            "DEFAULT_MODELS_ENDPOINT": "http://localhost:1",
            "EMBED_MODEL": "invented-model",
            "EMBED_API_KEY": "nvapi-your-api-key-here",
        },
    )
    before = path.read_bytes()
    monkeypatch.setattr(
        readers.urllib.request, "urlopen", Mock(side_effect=OSError("unavailable"))
    )
    with pytest.raises(OSError):
        readers.prepare_models(path)
    assert path.read_bytes() == before


def test_successful_embedding_probe_replaces_only_placeholder_keys(
    readers, monkeypatch, tmp_path
):
    path = tmp_path / "auto.env"
    readers.save_env(
        path,
        {
            "DEFAULT_MODELS_API_KEY": "invented-default",
            "DEFAULT_MODELS_ENDPOINT": "http://localhost:1",
            "EMBED_MODEL": "invented-model",
            "EMBED_API_KEY": "nvapi-your-api-key-here",
            "REASONING_API_KEY": "invented-explicit",
        },
    )
    response = Mock()
    response.read.return_value = b'{"data":[{"embedding":[1,2]}]}'
    context = Mock()
    context.__enter__ = Mock(return_value=response)
    context.__exit__ = Mock(return_value=False)
    probe = Mock(return_value=context)
    monkeypatch.setattr(readers.urllib.request, "urlopen", probe)
    readers.prepare_models(path)
    after = readers.load_env(path)
    assert after["EMBED_API_KEY"] == "invented-default"
    assert after["REASONING_API_KEY"] == "invented-explicit"
    assert (
        probe.call_args.args[0].get_header("Authorization") == "Bearer invented-default"
    )


@pytest.mark.parametrize(
    "readable,writable,tls", [(1, 1, True), (0, 0, True), (1, 0, False)]
)
def test_verify_rejects_writable_empty_or_unencrypted_sources(
    readers, monkeypatch, readable, writable, tls
):
    cursor = Mock()
    cursor.fetchone.side_effect = [(False,), (readable, writable), (tls,)]
    connection = Mock()
    connection.cursor.return_value.__enter__ = Mock(return_value=cursor)
    connection.cursor.return_value.__exit__ = Mock(return_value=False)
    context = Mock()
    context.__enter__ = Mock(return_value=connection)
    context.__exit__ = Mock(return_value=False)
    monkeypatch.setattr(readers.psycopg, "connect", Mock(return_value=context))
    with pytest.raises(ValueError):
        readers.verify("postgresql://reader:invented@localhost/catalog")


def test_saved_reader_cannot_silently_select_a_different_source(readers, tmp_path):
    path = tmp_path / "reader.env"
    readers.save_env(
        path,
        {
            "STORE_DATABASE_URL": "postgresql://reader:invented@localhost/old?sslmode=require"
        },
    )
    source = {
        "variable": "STORE_DATABASE_URL",
        "store": "rdm",
        "role": "reader",
    }
    with pytest.raises(ValueError, match="Saved reader differs"):
        readers.provision(
            source,
            {
                "DB_URL": "postgresql://owner:invented@localhost/new?sslmode=require"
            },
            path,
            exposure=EXPOSURE_FILE,
        )


def test_a_reader_is_granted_select_on_each_exposed_table_and_nothing_wider(readers, monkeypatch, tmp_path):
    """The reader holds the exposure list's tables by name: no schema-wide grant and no default privilege for a future table."""
    statements = []

    class Cursor:
        def __enter__(self):
            return self

        def __exit__(self, *_):
            return False

        def execute(self, query, params=None):
            statements.append(query.as_string(None) if hasattr(query, "as_string") else query)

        def fetchone(self):
            return None

    class Connection(Cursor):
        def cursor(self):
            return Cursor()

    monkeypatch.setattr(readers.psycopg, "connect", lambda *a, **k: Connection())
    monkeypatch.setattr(readers, "verify", lambda value, expected=None: {"expected": expected})
    source = {"variable": "RDM_DATABASE_URL", "store": "rdm", "role": "discovery_reader_rdm"}
    url, report = readers.provision(source, {"DB_URL": "postgresql://owner:x@h:5432"}, tmp_path / "reader.env", exposure=EXPOSURE_FILE)
    joined = "\n".join(str(s) for s in statements)
    assert report == {"expected": ["rdm.published_code"]}
    assert 'GRANT SELECT ON TABLE "rdm"."published_code"' in joined
    assert "ALL TABLES" not in joined and "DEFAULT PRIVILEGES" not in joined


def test_the_exposure_list_gives_each_stores_schema_and_tables(readers):
    assert readers.exposed(EXPOSURE_FILE, "mdm") == ("public", ["mastering_identifier", "mastering_master"])
    schema, tables = readers.exposed(EXPOSURE_FILE, "silver")
    assert schema == "silver" and "thirteenf_holding" in tables and len(tables) == 16
    with pytest.raises(ValueError, match="names no table"):
        readers.exposed(EXPOSURE_FILE, "rules")


def test_one_reader_login_serves_every_store_and_is_made_once(readers, monkeypatch, tmp_path):
    """The second store reuses the first's login and password: the role exists, its credentials are saved, so it is granted, not made again."""
    statements, exists = [], {"made": False}

    class Cursor:
        def __enter__(self):
            return self

        def __exit__(self, *_):
            return False

        def execute(self, query, params=None):
            text = query.as_string(None) if hasattr(query, "as_string") else query
            statements.append(text)
            if text.startswith("CREATE ROLE"):
                exists["made"] = True

        def fetchone(self):
            return (1,) if exists["made"] else None

    class Connection(Cursor):
        def cursor(self):
            return Cursor()

    monkeypatch.setattr(readers.psycopg, "connect", lambda *a, **k: Connection())
    monkeypatch.setattr(readers, "verify", lambda value, expected=None: {"expected": expected})
    reader = tmp_path / "reader.env"
    owner = {"DB_URL": "postgresql://owner:x@h:5432"}
    first = {"variable": "MDM_DATABASE_URL", "store": "mdm", "role": "discovery_reader"}
    second = {"variable": "RDM_DATABASE_URL", "store": "rdm", "role": "discovery_reader"}
    url1, _ = readers.provision(first, owner, reader, exposure=EXPOSURE_FILE)
    url2, _ = readers.provision(second, owner, reader, exposure=EXPOSURE_FILE)
    assert sum(s.startswith("CREATE ROLE") for s in statements) == 1  # one login
    a, b = readers.urlsplit(url1), readers.urlsplit(url2)
    assert (a.username, a.password) == (b.username, b.password) and (a.path, b.path) == ("/mdm", "/rdm")  # one credential, each store's database
    joined = "\n".join(statements)
    assert 'GRANT SELECT ON TABLE "rdm"."published_code"' in joined and 'GRANT SELECT ON TABLE "public"."mastering_master"' in joined
    assert "ALL TABLES" not in joined


def test_a_login_that_exists_with_no_saved_credentials_is_still_refused(readers, monkeypatch, tmp_path):
    class Cursor:
        def __enter__(self):
            return self

        def __exit__(self, *_):
            return False

        def execute(self, *_):
            pass

        def fetchone(self):
            return (1,)

    class Connection(Cursor):
        def cursor(self):
            return Cursor()

    monkeypatch.setattr(readers.psycopg, "connect", lambda *a, **k: Connection())
    source = {"variable": "RDM_DATABASE_URL", "store": "rdm", "role": "discovery_reader"}
    with pytest.raises(ValueError, match="without saved credentials"):
        readers.provision(source, {"DB_URL": "postgresql://owner:x@h:5432"}, tmp_path / "reader.env", exposure=EXPOSURE_FILE)
