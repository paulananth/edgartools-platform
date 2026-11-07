"""Every database statement of mastering. The merge never sees SQL, and the two engines differ here only."""

from __future__ import annotations

import io
import json
from collections import defaultdict
from pathlib import Path

BLOCK = 2000
LOCK = "merge"
WRITTEN = ("master", "file", "identifier", "record", "name_key", "review", "withheld", "deferred",
           "stage", "stage_key", "stage_bound", "lookup", "lookup_progress")


def marks(items) -> str:
    return ",".join(["%s"] * len(items))


def blocks(items):
    items = list(items)
    for at in range(0, len(items), BLOCK):
        yield items[at:at + BLOCK]


class Store:
    dialect = ""
    ignore = ""
    conflict_nothing = ""

    def __init__(self, connection):
        self.connection = connection
        self.cursor = connection.cursor()

    def commit(self) -> None:
        self.connection.commit()

    def rollback(self) -> None:
        self.connection.rollback()

    def close(self) -> None:
        self.connection.close()

    def rows(self, sql: str, values=()) -> list[tuple]:
        self.cursor.execute(sql, list(values))
        return list(self.cursor.fetchall())

    def insert(self, table: str, columns: tuple, rows: list) -> None:
        for block in blocks(rows):
            one = "(" + marks(columns) + ")"
            self.cursor.execute(f"insert {self.ignore} into {table}({','.join(columns)}) values "
                                + ",".join([one] * len(block)) + self.conflict_nothing,
                                [value for row in block for value in row])

    def take_lock(self) -> None:
        """One writer for a whole file. The database frees it when the writer commits or dies."""
        self.create_lock()
        self.commit()
        self.rows("select name from mastering_lock where name=%s for update", [LOCK])

    def file_done(self, key: str) -> bool:
        return bool(self.rows("select 1 from mastering_file where file_key=%s", [key]))

    def done_files(self, keys) -> dict:
        found = {}
        for block in blocks(keys):
            found.update(self.rows(f"select file_key,records from mastering_file where file_key in ({marks(block)})", block))
        return found

    def finish_file(self, key: str, records: int) -> None:
        self.cursor.execute("insert into mastering_file(file_key,records) values (%s,%s)", [key, records])

    def last_file(self) -> int:
        return self.rows("select coalesce(max(changed_file),0) from mastering_master")[0][0]

    def load_stage(self, records: list, name_keys: list) -> None:
        self.cursor.execute("delete from mastering_stage")
        self.bulk("mastering_stage", ("assertion_id", "subject", "source_code", "lei", "body"), records)
        if name_keys:
            self.insert("mastering_name_key", ("role", "lei", "subject"), name_keys)

    def holders(self, wanted: dict) -> list[tuple]:
        """Who holds each wanted identifier, by a plain join to the stage."""
        self.cursor.execute("delete from mastering_stage_key")
        self.bulk("mastering_stage_key", ("namespace", "value"), [(n, v) for n, values in wanted.items() for v in values])
        return self.rows("select distinct i.namespace,i.value,i.entity_id from mastering_identifier i "
                         "join mastering_stage_key s on s.namespace=i.namespace and s.value=i.value")

    def add_identifiers(self, rows: list) -> None:
        if rows:
            self.insert("mastering_identifier", ("namespace", "value", "entity_id"), rows)

    def bound(self, subjects) -> dict:
        found = {}
        for block in blocks(subjects):
            found.update(self.rows("select subject,entity_id from mastering_record "
                                   f"where entity_id is not null and subject in ({marks(block)})", block))
        return found

    def members_bound(self, entities) -> dict:
        found = {}
        for block in blocks(entities):
            found.update(self.rows(f"select subject,entity_id from mastering_record where entity_id in ({marks(block)})", block))
        return found

    def member_bodies(self, entities) -> list[str]:
        found = []
        for block in blocks(entities):
            found += [row[0] for row in self.rows(f"select body from mastering_record where entity_id in ({marks(block)})", block)]
        return found

    def oldest(self, entities) -> list[str]:
        return [row[0] for row in self.rows(f"select entity_id from mastering_master where entity_id in ({marks(entities)}) "
                                            "order by created_at,entity_id", list(entities))]

    def repoint(self, keep: str, gone: str) -> None:
        for table in ("mastering_identifier", "mastering_record"):
            self.cursor.execute(f"update {table} set entity_id=%s where entity_id=%s", [keep, gone])

    def split(self, keep: str, gone: str) -> list[tuple]:
        """A merged-away master's records return to it: a record keeps the master it was first bound to."""
        self.cursor.execute("update mastering_record set entity_id=%s where entity_id=%s and bound_id=%s", [gone, keep, gone])
        self.cursor.execute("delete from mastering_identifier where entity_id=%s", [keep])
        return self.rows("select subject,entity_id,body from mastering_record where entity_id in (%s,%s)", [keep, gone])

    def name_pairs(self, role: str, holder_source: str, source: str, holders: list) -> list[tuple]:
        """(candidate, holder) bodies: a waiting candidate with a holder of this file, then a candidate of this file."""
        found = []
        if holders:
            found += self.rows("select c.body,h.body from mastering_stage h join mastering_name_key k on k.role=%s and k.subject=h.subject "
                               "join mastering_record c on c.lei=k.lei and c.entity_id is null "
                               f"where h.source_code=%s and c.source_code=%s and h.subject in ({marks(holders)})",
                               [role, holder_source, source, *holders])
        for table in ("mastering_stage", "mastering_record"):
            found += self.rows("select c.body,h.body from mastering_stage c join mastering_name_key k on k.role=%s and k.lei=c.lei "
                               f"join {table} h on h.subject=k.subject and h.source_code=%s where c.source_code=%s",
                               [role, holder_source, source])
        return list(set(found))

    def lei_held(self, entities) -> dict:
        held = defaultdict(set)
        for entity, value in self.rows("select entity_id,value from mastering_identifier where namespace='lei' "
                                       f"and entity_id in ({marks(entities)})", list(entities)):
            held[entity].add(value)
        return held

    def save_records(self, bound: dict) -> None:
        """The file's records with their masters, in one write. Older rows of the same subjects follow."""
        self.cursor.execute("delete from mastering_stage_bound")
        self.bulk("mastering_stage_bound", ("subject", "entity_id"), list(bound.items()))
        self.cursor.execute(f"insert {self.ignore} into mastering_record(assertion_id,subject,entity_id,bound_id,source_code,lei,body) "
                            "select s.assertion_id,s.subject,b.entity_id,b.entity_id,s.source_code,s.lei,s.body from mastering_stage s "
                            "left join mastering_stage_bound b on b.subject=s.subject" + self.conflict_nothing)
        older = self.rows("select r.assertion_id,b.entity_id from mastering_stage_bound b join mastering_record r "
                          "on r.subject=b.subject where r.entity_id is null or r.entity_id<>b.entity_id")
        self.cursor.executemany("update mastering_record set bound_id=coalesce(bound_id,%s),entity_id=%s where assertion_id=%s",
                                [(entity, entity, assertion) for assertion, entity in older])

    def add_decision(self, body: dict, left, right) -> None:
        self.insert("mastering_decision", ("decision_id", "operation", "left_id", "right_id", "body"),
                    [(body["decision_id"], body["operation"], left, right, json.dumps(body))])

    def decisions_about(self, entities) -> list[dict]:
        return [json.loads(row[0]) for row in self.rows(
            "select body from mastering_decision where operation in ('merge','exclude','reverse') "
            f"and (left_id in ({marks(entities)}) or right_id in ({marks(entities)}))", [*entities, *entities])]

    def merges(self) -> list[tuple]:
        return self.rows("select decision_id,left_id,right_id from mastering_decision where operation='merge' "
                         "and decision_id not in (select right_id from mastering_decision where operation='reverse')")

    def overrides(self, subjects) -> list[dict]:
        found = []
        for block in blocks(subjects):
            found += [json.loads(row[0]) for row in self.rows(
                f"select d.body from mastering_decision d where d.operation='override' and d.left_id in ({marks(block)}) "
                "and d.decision_id not in (select right_id from mastering_decision where operation='revoke')", block)]
        return found

    def add_withheld(self, rows: list) -> None:
        if rows:
            self.insert("mastering_withheld", ("subject", "namespace", "raw"), rows)

    def withheld(self, subjects) -> dict:
        found = defaultdict(list)
        for block in blocks(subjects):
            for subject, namespace, raw in self.rows(
                    f"select subject,namespace,raw from mastering_withheld where subject in ({marks(block)})", block):
                found[subject].append({"namespace": namespace, "raw": raw})
        return dict(found)

    def close_reviews(self, reason: str, subjects) -> None:
        for block in blocks(subjects):
            self.cursor.execute(f"update mastering_review set open_review=0 where reason=%s and subject in ({marks(block)})", [reason, *block])

    def open_reviews(self, reason: str, rows: list) -> None:
        for block in blocks(rows):
            self.cursor.execute("insert into mastering_review(subject,reason,assertion_id,open_review) values "
                                + ",".join(["(%s,%s,%s,1)"] * len(block)) + self.review_upsert,
                                [value for subject, assertion in block for value in (subject, reason, assertion)])

    def add_deferred(self, rows: list) -> None:
        if rows:
            self.insert("mastering_deferred", ("deferred_id", "source_code", "reason", "blocking", "body"), rows)

    def write_masters(self, rows: list, file_no: int) -> None:
        for block in blocks(rows):
            self.cursor.execute("insert into mastering_master(entity_id,body,changed_file) values "
                                + ",".join(["(%s,%s,%s)"] * len(block)) + self.master_upsert,
                                [value for entity, body in block for value in (entity, body, file_no)])

    def changes(self, since: int, after: str = "", limit: int = 1000) -> list[tuple]:
        """One page of what changed after a reader's checkpoint: (file, master id, body)."""
        page = "select changed_file,entity_id,body from mastering_master where {} order by changed_file,entity_id limit %s"
        rows = self.rows(page.format("changed_file=%s and entity_id>%s"), [since, after, limit]) if after else []
        if len(rows) < limit:
            rows += self.rows(page.format("changed_file>%s"), [since, limit - len(rows)])
        return rows

    def master_bodies(self, entities) -> dict:
        found = {}
        for block in blocks(entities):
            found.update((e, json.loads(b)) for e, b in self.rows(
                f"select entity_id,body from mastering_master where entity_id in ({marks(block)})", block))
        return found

    def cross_referenced(self, entities) -> list[tuple]:
        """Each master's member records that carry a cross-reference: (master id, record body)."""
        found = []
        for block in blocks(entities):
            found += self.rows("select entity_id,body from mastering_record where body like %s "
                               f"and entity_id in ({marks(block)})", ['%"cross_references":{"%', *block])
        return found

    def lookup_progress(self, pin: str) -> tuple:
        """Where the lookups built under `pin` have reached: (changed file, last master id)."""
        found = self.rows("select changed_file,entity_id from mastering_lookup_progress where pin=%s", [pin])
        return found[0] if found else (-1, "")

    def save_lookups(self, pin: str, entities: list, rows: list, reached: tuple) -> None:
        for block in blocks(entities):
            self.cursor.execute(f"delete from mastering_lookup where entity_id in ({marks(block)})", block)
        self.bulk("mastering_lookup", ("token", "entity_id"), rows)
        self.cursor.execute("delete from mastering_lookup_progress where pin=%s", [pin])
        self.cursor.execute("insert into mastering_lookup_progress(pin,changed_file,entity_id) values (%s,%s,%s)",
                            [pin, *reached])

    def masters_containing(self, text: str, limit: int) -> list:
        """Masters whose stored text holds this, up to the limit."""
        like = text.replace("|", "||").replace("%", "|%").replace("_", "|_")
        return self.rows("select entity_id,body from mastering_master where lower(body) like %s escape '|' limit %s",
                         [f"%{like}%", limit])

    def holding_all(self, tokens: list) -> list[str]:
        """The masters holding every token."""
        tokens = sorted(set(tokens))
        return [row[0] for row in self.rows(
            f"select entity_id from mastering_lookup where token in ({marks(tokens)}) "
            "group by entity_id having count(*)=%s order by entity_id", [*tokens, len(tokens)])]

    def records_named(self, assertions) -> dict:
        """Each named record's source and key: {assertion id: (source code, record key)}."""
        found = {}
        for block in blocks(assertions):
            found.update((assertion, (source, json.loads(body)["record_key"])) for assertion, source, body in self.rows(
                f"select assertion_id,source_code,body from mastering_record where assertion_id in ({marks(block)})", block))
        return found

    def master_file(self, entity: str) -> int:
        return self.rows("select changed_file from mastering_master where entity_id=%s", [entity])[0][0]

    def identifier_holders(self, namespace: str, values) -> list[str]:
        return [row[0] for row in self.rows(
            f"select distinct entity_id from mastering_identifier where namespace=%s and value in ({marks(values)})",
            [namespace, *values])]

    def totals(self) -> dict:
        masters = self.rows("select count(distinct entity_id) from mastering_record where entity_id is not null")[0][0]
        waiting = self.rows("select count(*) from mastering_review where reason=%s and open_review=1", ["binding_required"])[0][0]
        return {"masters": masters, "waiting": waiting, "set_aside": self.rows("select count(*) from mastering_deferred")[0][0]}


class Postgres(Store):
    dialect = "postgresql"
    conflict_nothing = " on conflict do nothing"
    master_upsert = (" on conflict(entity_id) do update set body=excluded.body,changed_file=excluded.changed_file "
                     "where mastering_master.body<>excluded.body")
    review_upsert = " on conflict(subject,reason) do update set assertion_id=excluded.assertion_id,open_review=1"

    def create_lock(self) -> None:
        self.cursor.execute("insert into mastering_lock(name) values (%s) on conflict do nothing", [LOCK])

    def bulk(self, table: str, columns: tuple, rows: list) -> None:
        def clean(value):
            return "\\N" if value is None else value.replace("\\", "\\\\").replace("\t", "\\t").replace("\n", "\\n")
        text = io.StringIO("".join("\t".join(clean(value) for value in row) + "\n" for row in rows))
        self.cursor.copy_expert(f"copy {table}({','.join(columns)}) from stdin", text)


class MySQL(Store):
    dialect = "mysql"
    ignore = "ignore"
    master_upsert = (" as new on duplicate key update changed_file="
                     "if(mastering_master.body=new.body,mastering_master.changed_file,new.changed_file),body=new.body")
    review_upsert = " as new on duplicate key update assertion_id=new.assertion_id,open_review=1"

    def create_lock(self) -> None:
        self.cursor.execute("insert ignore into mastering_lock(name) values (%s)", [LOCK])

    def bulk(self, table: str, columns: tuple, rows: list) -> None:
        self.insert(table, columns, rows)


def open_store(engine) -> Store:
    selected = {"postgresql": Postgres, "mysql": MySQL}.get(engine.dialect.name)
    if selected is None:
        raise ValueError("Mastering supports PostgreSQL and MySQL")
    return selected(engine.raw_connection())


def install(engine, *, runtime_role: str) -> None:
    """Create the tables, then let the runtime merge without changing structure or decisions."""
    source = (Path(__file__).parent / "schema" / f"{engine.dialect.name}.sql").read_text()
    grantee = f'"{runtime_role}"' if engine.dialect.name == "postgresql" else f"'{runtime_role}'@'%%'"
    with engine.begin() as conn:
        for statement in source.split(";"):
            if statement.strip():
                conn.exec_driver_sql(statement)
        for name in WRITTEN:
            conn.exec_driver_sql(f"grant select,insert,update,delete on mastering_{name} to {grantee}")
        conn.exec_driver_sql(f"grant select,insert on mastering_decision to {grantee}")
        conn.exec_driver_sql(f"grant select,insert,update on mastering_lock to {grantee}")
