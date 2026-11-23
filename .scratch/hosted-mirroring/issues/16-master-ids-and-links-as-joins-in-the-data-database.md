# 16: Master ids and links as joins inside the data database

Status: open
Type: grilling

Follow-up named by hosted-mirroring ticket 04 and carried by ticket 14. Nothing is decided yet.

## Question

MDM, RDM and silver now share one data database (schemas `mdm`, `rdm`, `silver`). A silver table with an MDM id column is filled from the
golden records, and a relationship links two masters. Should the master id on a silver row, and a link between two masters, be read as a join
inside the data database (so the mirror carries the tables and Gold joins them), or stay written onto the row by a step of the load?

## Checklist

- [x] Read how the id is filled and the links are written today, and what Gold reads from the mirror 2026-11-22 20:53 ET. Findings:
      - A silver spec's `links` name each master link's `mdm_id_column`; the table gets that text column (`silver_writer/database.py`, `spec.py`).
      - The writer fills it at landing from MDM's bound keys (`writer.py` via `mastering/reads.master_ids`, or `sole_holders` for an identifier link), and `--finish` refreshes only rows whose id is still empty (`refresh_ids`, `set_ids`). It opens the MDM store through its own connection (`open_store`), so the id is a value copied onto the row.
      - Relationships are rows of `relationship` (source and target master ids, a period), built whole by `silver links`; the mirror carries them (`sources/managed-mirror.yaml`).
      - Gold already joins in the mirror: `gold/views.py` joins each silver fact's `mdm_id` column to `mdm.mastering_master` (`dim_*` views) and to `mdm.mastering_identifier`; it never reads the written id's source key. So the written id is what Gold joins on.
- [x] Decided with the operator, 2026-11-22: "join using the master id why do you need other ids", then "kiss and 7 wastes keep it clean": a join inside the data database, the master id the only id that crosses; no written id column, no refresh step, no second id 2026-11-22 20:58 ET
- [ ] Name the tables, keys and the Gold view change as a code ticket, keeping it minimal (one join, nothing added beside it): which MDM table binds a silver key to its master, what retires (`mdm_id_column`, `refresh_ids`, `set_ids`, the `--finish` fill), and how a merged-away id resolves to its survivor
- [ ] Learning → skill: name the skill line this ticket changed, or "none"
