"""`edgar-warehouse context silver [<table>]`: a silver table for agents (profiling
tickets 05 and 06). Read through `silver.table_context`, from the spec the table
was created from: what one row is, its key, its links to masters (and the column
holding each master's MDM id), its time columns and load mode, in JSON of at
most 8 KB (the command's own rules: `edgar_warehouse/context.py`). Without a
table, it lists the tables."""

from __future__ import annotations

import argparse
import shlex

from sqlalchemy import text

from edgar_warehouse.context import PROG, ContextError, fit, page_offset

VIEW = "silver.table_context WHERE table_name = '<table>'"


class TableContext:
    """Silver tables, read from the silver schema through a read-only connection."""

    def __init__(self, engine):
        self.engine = engine

    def answer(self, args: argparse.Namespace) -> dict:
        if args.as_of or args.as_at or args.search is not None or args.hops != 1 or args.relationship_type:
            raise ContextError("A silver table answers with its spec: --search, --as-of, --as-at, --hops and --type "
                               "are for masters, codes and relationships.", f"{PROG} silver <table>")
        with self.engine.connect() as conn:
            if not args.key:
                tables = [dict(r) for r in conn.execute(text(
                    "SELECT table_name, grain, load_mode FROM silver.table_context ORDER BY table_name")).mappings()]
                answer = {"name": "silver tables", "kind": "silver", "tables": tables, "truncated": False,
                          "next_page": None, "next_step": f"{PROG} silver <table_name>"}
                return fit(answer, "tables", page_offset(args.page), f"{PROG} silver", "silver.table_context")
            row = conn.execute(text("SELECT * FROM silver.table_context WHERE table_name = :t"),
                               {"t": args.key}).mappings().first()
        if row is None:
            raise ContextError(f"No silver table {args.key!r}.", f"{PROG} silver")
        answer = {
            "name": row["table_name"],
            "kind": "silver table",
            "key": row["key"],
            "definition": row["definition"],
            "grain": row["grain"],
            "links": row["links"],
            "time": row["time_columns"],
            "load_mode": row["load_mode"],
            "trust": {"source": "silver", "spec_ref": row["spec_ref"], "registered_at": row["registered_at"].isoformat()},
            "truncated": False,
            "next_page": None,
            "next_step": f"SELECT * FROM silver.{_quoted(row['table_name'])} LIMIT 10",
        }
        return fit(answer, "links", page_offset(args.page), f"{PROG} silver {shlex.quote(args.key)}", VIEW)


def _quoted(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'
