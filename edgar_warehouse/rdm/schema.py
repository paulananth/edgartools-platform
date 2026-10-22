"""Compile the logical reference schema and its destination integrity guards.

Used to prepare a new frozen migration, never to regenerate an installed one.
The caller's lifecycle and publication algorithm is shared between engines.
"""
from sqlalchemy import CheckConstraint, Column, Computed, ForeignKeyConstraint, String
from sqlalchemy.dialects import mysql
from sqlalchemy.schema import CreateIndex, CreateTable

from .storage import KEYS, tables


def _hash(fields, prefix=""):
    return "sha2(cast(json_array(" + ",".join(prefix + "`" + f + "`" for f in fields) + ") as binary),256)"


def _ref(table, name, fields, target, *, nullable=None):
    expression = _hash(fields)
    if nullable:
        expression = "case when `" + nullable + "` is null then null else " + expression + " end"
    table.append_column(Column(name, String(64, collation="ascii_bin"), Computed(expression, persisted=True)))
    table.append_constraint(ForeignKeyConstraint([name], [target + "._row_key"]))


def _fail(condition, message):
    return "IF " + condition + " THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='" + message.replace("'", "''") + "'; END IF;"


def _changed(fields):
    return " OR ".join("NOT (NEW.`" + f + "` <=> OLD.`" + f + "`)" for f in fields)


def mysql_statements():
    # A private copy: compiling migrations must not mutate the cached caller model.
    from sqlalchemy import MetaData

    metadata = MetaData()
    models = {name: table.to_metadata(metadata) for name, table in tables("mysql").items()}
    checks = {
        "code_set": ["REGEXP_LIKE(code_set,'^[a-z0-9][a-z0-9_.-]*$','c')", "trim(name)<>''"],
        "code_set_version": ["REGEXP_LIKE(version,'^[A-Za-z0-9][A-Za-z0-9_.-]*$','c')",
            "status IN ('draft','approved','published','retired')", "trim(created_by)<>''",
            "valid_to IS NULL OR valid_to>=valid_from", "JSON_VALID(evidence) AND JSON_TYPE(evidence)='OBJECT'",
            "sha256 IS NULL OR REGEXP_LIKE(sha256,'^[0-9a-f]{64}$','c')"],
        "code": ["code<>''", "status IN ('valid','invalid')", "valid_to IS NULL OR valid_to>=valid_from",
            "(status='invalid')=(invalid_reason IS NOT NULL)", "parent_code IS NULL OR parent_code<>code"],
        "code_label": ["REGEXP_LIKE(language,'^[a-z]{2,3}(-[A-Za-z0-9]+)*$','c')",
            "trim(label)<>''", "kind IN ('preferred','synonym')"],
        "level": ["depth>=1", "trim(name)<>''"],
        "code_path": ["depth>=1"],
        "crosswalk_row": ["REGEXP_LIKE(to_set,'^[a-z0-9][a-z0-9_.-]*$','c')", "trim(to_version)<>''",
            "to_code<>''", "match_type IN ('exact','close','broad','narrow')",
            "JSON_VALID(evidence) AND JSON_TYPE(evidence)='OBJECT'"],
        "code_set_usage": ["store IN ('mdm','silver','source','other')", "trim(`object`)<>''",
            "trim(field)<>''", "`match` IN ('exact','upper_trimmed')"],
        "code_set_hint": ["kind IN ('meaning','use_when','avoid_when','example_question')",
            "ordinal>=1", "trim(text)<>''"],
    }
    for name, table in models.items():
        for i, condition in enumerate(checks[name]):
            table.append_constraint(CheckConstraint(condition, name=name + "_check_" + str(i)))
        if name == "code_set_version":
            _ref(table, "_catalog_key", ("code_set",), "code_set")
            _ref(table, "_supersedes_key", ("code_set", "supersedes"), "code_set_version", nullable="supersedes")
        elif name != "code_set":
            table.append_constraint(ForeignKeyConstraint(["_version_key"], ["code_set_version._row_key"]))
        if name in {"code_label", "code_path", "crosswalk_row"}:
            fields = ("from_set", "from_version", "from_code") if name == "crosswalk_row" else ("code_set", "version", "code")
            _ref(table, "_code_key", fields, "code")
        if name == "code":
            _ref(table, "_parent_key", ("code_set", "version", "parent_code"), "code", nullable="parent_code")
    dialect = mysql.dialect()
    statements = []
    # MySQL self FKs are legal at CREATE; other parents precede children.
    for name in KEYS:
        table = models[name]
        statements.append(str(CreateTable(table, if_not_exists=True).compile(dialect=dialect)).strip())
        statements.extend(str(CreateIndex(index).compile(dialect=dialect)).strip()
                          for index in sorted(table.indexes, key=lambda index: index.name))

    draft_insert = _fail("NEW.status<>'draft' OR NEW.approved_by IS NOT NULL OR NEW.approved_words IS NOT NULL "
        "OR NEW.approved_at IS NOT NULL OR NEW.published_at IS NOT NULL OR NEW.sha256 IS NOT NULL "
        "OR NEW.valid_from IS NOT NULL OR NEW.valid_to IS NOT NULL", "A new version must be an unapproved draft")
    governance = [
        _fail(_changed(("code_set", "version", "created_by", "created_at", "supersedes", "_row_key")),
              "A version's identity is immutable"),
        _fail("OLD.status<>'draft' AND NOT (NEW.evidence <=> OLD.evidence)", "Evidence is fixed once a version is approved"),
        _fail("FIELD(NEW.status,'draft','approved','published','retired') < FIELD(OLD.status,'draft','approved','published','retired') "
              "OR FIELD(NEW.status,'draft','approved','published','retired') > FIELD(OLD.status,'draft','approved','published','retired')+1",
              "Invalid reference data lifecycle transition"),
        "IF " + _changed(("approved_by", "approved_words", "approved_at")) + " THEN "
            + _fail("OLD.status<>'draft' OR NEW.status<>'approved'", "Approval is recorded once, on a draft")
            + " SET NEW.approved_at=UTC_TIMESTAMP(6); END IF;",
        _fail("NEW.status='approved' AND (trim(coalesce(NEW.approved_by,''))='' OR trim(coalesce(NEW.approved_words,''))='')",
              "An approval names who approved and holds their exact words"),
        _fail("NEW.status='approved' AND OLD.status='draft' AND NEW.approved_by=NEW.created_by", "The drafter cannot approve its own draft"),
        _fail("(" + _changed(("sha256", "published_at", "valid_from")) + ") AND (OLD.status<>'approved' OR NEW.status<>'published')",
              "The sha256 and valid_from are set once, when published"),
        "IF NEW.status='published' AND OLD.status='approved' THEN "
            + _fail("NEW.sha256 IS NULL OR NEW.valid_from IS NULL", "Publishing needs the sha256 and valid_from")
            + " SELECT v.version INTO replaced FROM code_set_version v WHERE v._set_key=" + _hash(("code_set",), "NEW.")
            + " AND v.code_set=NEW.code_set AND v.status IN ('published','retired') AND v.version<>NEW.version "
              "ORDER BY v.valid_from DESC LIMIT 1; "
            + _fail("NOT (NEW.supersedes <=> replaced)", "A published version must supersede the version it replaces")
            + _fail("EXISTS (SELECT 1 FROM code c WHERE c._version_key=NEW._row_key AND c.code_set=NEW.code_set "
                    "AND c.version=NEW.version AND NOT EXISTS (SELECT 1 FROM code_path p WHERE p._row_key=c._row_key "
                    "AND p.code_set=c.code_set AND p.version=c.version AND p.code=c.code))", "Publishing needs a path for every code")
            + " SET NEW.published_at=UTC_TIMESTAMP(6); END IF;",
        _fail("NOT (NEW.valid_to <=> OLD.valid_to) AND (OLD.valid_to IS NOT NULL OR OLD.status<>'published')",
              "valid_to is set once, on a published version"),
        "IF NEW.status='retired' AND OLD.status='published' AND NEW.valid_to IS NULL THEN SET NEW.valid_to=UTC_TIMESTAMP(6); END IF;",
    ]
    for name in KEYS:
        for action in ("INSERT", "UPDATE", "DELETE"):
            trigger = name + "_" + action.lower() + "_guard"
            statements.append("DROP TRIGGER IF EXISTS `" + trigger + "`")
            declarations = ""
            body = []
            if action == "INSERT":
                body.append("SET NEW._row_key=" + _hash(KEYS[name], "NEW.") + ";")
            elif action == "UPDATE":
                body.append(_fail(_changed(("_row_key",)), "A row's storage key is immutable"))
                # Recompute on UPDATE for mutable draft keys; content identity
                # may change within its own version but cannot forge a key.
                body.append("SET NEW._row_key=" + _hash(KEYS[name], "NEW.") + ";")
            if name in {"code", "code_label"} and action != "DELETE":
                body.append("SET NEW._search_text=NEW.label;")
            if name == "code_set":
                if action != "INSERT":
                    body.append(_fail("TRUE", "Code set words are immutable"))
            elif name == "code_set_version":
                declarations = "DECLARE replaced LONGTEXT DEFAULT NULL;"
                body.extend([draft_insert] if action == "INSERT" else governance if action == "UPDATE"
                            else [_fail("TRUE", "Reference data history is retained")])
            else:
                declarations = "DECLARE held_status LONGTEXT DEFAULT NULL;"
                fields = ("from_set", "from_version") if name == "crosswalk_row" else ("code_set", "version")
                prefix = "OLD." if action == "DELETE" else "NEW."
                if action == "UPDATE":
                    body.append(_fail(_changed(fields), "A row stays in its version"))
                body.append("SELECT status INTO held_status FROM code_set_version WHERE _row_key=" + _hash(fields, prefix)
                    + " AND code_set=" + prefix + "`" + fields[0] + "` AND version=" + prefix + "`" + fields[1]
                    + "` FOR SHARE;")
                if name == "code_path":
                    body.append(_fail("TRUE" if action != "INSERT" else "NOT (held_status <=> 'approved')",
                                      "Paths are written once, while an approved version is published"))
                else:
                    body.append(_fail("NOT (held_status <=> 'draft')", "Only a draft version's content may change"))
            statements.append("CREATE TRIGGER `" + trigger + "` BEFORE " + action + " ON `" + name
                              + "` FOR EACH ROW BEGIN " + declarations + "\n" + "\n".join(body) + "\nEND")
    statements.extend([
        "DROP PROCEDURE IF EXISTS lock_code_set",
        "CREATE PROCEDURE lock_code_set(IN wanted_set LONGTEXT) SQL SECURITY DEFINER BEGIN "
        "DECLARE held LONGTEXT; SELECT code_set INTO held FROM code_set WHERE _row_key="
        + _hash(("wanted_set",)).replace("`wanted_set`", "wanted_set")
        + " AND code_set=wanted_set FOR UPDATE; END",
        "CREATE OR REPLACE SQL SECURITY INVOKER VIEW code_context AS SELECT "
        "c._row_key,c.code_set,s.name AS code_set_name,c.code,c.label,c.definition,"
        "coalesce((SELECT JSON_ARRAYAGG(l.label) FROM code_label l WHERE l._version_key=c._version_key "
        "AND l.code_set=c.code_set AND l.version=c.version AND l.code=c.code AND l.kind='synonym'),JSON_ARRAY()) AS synonyms,"
        "p.path,p.label_path,p.level,p.depth,c.parent_code,"
        "coalesce((SELECT JSON_ARRAYAGG(JSON_OBJECT('to_set',x.to_set,'to_version',x.to_version,'to_code',x.to_code,"
        "'match_type',x.match_type)) FROM crosswalk_row x WHERE x._code_key=c._row_key "
        "AND x.from_set=c.code_set AND x.from_version=c.version AND x.from_code=c.code),JSON_ARRAY()) AS crosswalk,"
        "c.version,v.sha256,v.valid_from,v.valid_to,v.status AS version_status,c.status AS code_status,"
        "c.valid_from AS code_valid_from,c.valid_to AS code_valid_to,c.invalid_reason,v.approved_by,v.approved_at,v.published_at "
        "FROM code c JOIN code_set_version v ON v._row_key=c._version_key AND v.code_set=c.code_set AND v.version=c.version "
        "JOIN code_set s ON s._row_key=v._catalog_key AND s.code_set=c.code_set "
        "JOIN code_path p ON p._row_key=c._row_key AND p.code_set=c.code_set AND p.version=c.version AND p.code=c.code "
        "WHERE v.status IN ('published','retired')",
    ])
    return statements
