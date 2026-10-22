"""`edgar-warehouse context silver [<table>]`: a silver table for agents (profiling
tickets 05 and 06). Read through `silver.table_context`, from the spec the table
was created from: what one row is, its key, its links to masters (and the column
holding each master's MDM id), its time columns and load mode, in JSON of at
most 8 KB (the command's own rules: `edgar_warehouse/context.py`). Without a
table, it lists the tables."""

from __future__ import annotations

import argparse
import shlex

from edgar_warehouse.context import PROG, ContextError, fit, page_offset

from .storage import registered

VIEW = "silver.table_context WHERE table_name = '<table>'"


class TableContext:
    """Silver tables, read from the silver schema through a read-only connection."""

    def __init__(self, engine):
        self.engine = engine

    def answer(self, args: argparse.Namespace) -> dict:
        if args.as_of or args.as_at or args.search is not None or args.hops != 1 or args.relationship_type:
            raise ContextError("A silver table answers with its spec: --search, --as-of, --as-at, --hops and --type "
                               "are for masters, codes and relationships.", f"{PROG} silver <table>")
        if not args.key:
            answer = {"name": "silver tables", "kind": "silver", "tables": self.table(None), "truncated": False,
                      "next_page": None, "next_step": f"{PROG} silver <table_name>"}
            return fit(answer, "tables", page_offset(args.page), f"{PROG} silver", "silver.table_context")
        return fit(self.table(args.key), "links", page_offset(args.page), f"{PROG} silver {shlex.quote(args.key)}", VIEW)

    def table(self, name: str | None) -> dict | list[dict]:
        """One table's spec as an agent reads it, or every table in a line each."""
        rows = registered(self.engine, name)
        if name is None:
            return [{"table_name": row["table_name"], "grain": row["spec"]["grain"],
                     "load_mode": row["spec"]["load_mode"]} for row in rows]
        row = rows[0] if rows else None
        if row is None:
            raise ContextError(f"No silver table {name!r}.", f"{PROG} silver")
        spec = row["spec"]
        links = [{key: link.get(key) for key in
                  ("columns", "kind", "source_code", "source_key", "mdm_id_column", "inclusion")}
                 for link in spec["links"] or []]
        quote = self.engine.dialect.identifier_preparer.quote_identifier
        target = "silver." + quote(row["table_name"]) if self.engine.dialect.name == "postgresql" else quote(row["table_name"])
        return {
            "name": row["table_name"],
            "kind": "silver table",
            "key": spec["key"],
            "definition": spec.get("definition") or spec["why"],
            "grain": spec["grain"],
            "links": links,
            "time": spec["time"],
            "load_mode": spec["load_mode"],
            "trust": {"source": "silver", "spec_ref": f"silver.table_spec/{name}@{row['sha256']}", "registered_at": row["registered_at"].isoformat()},
            "truncated": False,
            "next_page": None,
            "next_step": f"SELECT * FROM {target} LIMIT 10",
        }
