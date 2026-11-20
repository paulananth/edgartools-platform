"""The ownership SQL is written from the names file's owner and the databases the caller names; nothing connects."""
import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("database_owner_sql", ROOT / "skills/aws-snowflake-operations/scripts/database_owner_sql.py")
database_owner_sql = importlib.util.module_from_spec(spec)
spec.loader.exec_module(database_owner_sql)


def test_the_owner_role_is_created_held_by_the_administrator_and_given_each_database_with_its_grants():
    sql = database_owner_sql.statements("INVENTED_OWNER", ["DB_ONE", "DB_TWO"], "INVENTED_ADMIN")
    assert sql.splitlines() == [
        "CREATE ROLE IF NOT EXISTS INVENTED_OWNER;",
        "GRANT ROLE INVENTED_OWNER TO ROLE INVENTED_ADMIN;",
        "GRANT OWNERSHIP ON DATABASE DB_ONE TO ROLE INVENTED_OWNER COPY CURRENT GRANTS;",
        "GRANT OWNERSHIP ON DATABASE DB_TWO TO ROLE INVENTED_OWNER COPY CURRENT GRANTS;",
    ]


def test_the_owner_comes_from_the_names_file(tmp_path):
    names = tmp_path / "names.yaml"
    names.write_text("owner: FROM_FILE\n")
    out = database_owner_sql.main(["--names", str(names), "--database", "D", "--administrator-role", "A"])
    assert "TO ROLE FROM_FILE COPY CURRENT GRANTS" in out
