---
name: sql-writer
description: Render SQL for the database named by a connection. Use SQLAlchemy or SQLGlot so PostgreSQL, MySQL and SQL Server Express get their own dialect. Use when a skill or command must create a table, a migration statement, or a query on more than one engine. Do not paste SQL into a skill.
---

# SQL writer

This skill renders SQL. It does not store SQL. A skill that needs a statement
for PostgreSQL, MySQL, or SQL Server Express calls this skill. The statement
is compiled for the connection's dialect and then run. It is not copied into
the skill text.

## Which library

Use the library that already matches the job.

| Job | Library | Why |
|---|---|---|
| Create or alter a table from a logical spec or a SQLAlchemy model | SQLAlchemy 2 `CreateTable` / `CreateIndex`, compiled with `engine.dialect` | One model, one compiler per dialect. PostgreSQL, MySQL, and SQL Server (the `mssql` dialect) are built in. |
| Restate one standard statement from one dialect into another | [SQLGlot](https://github.com/tobymao/sqlglot) `transpile` | Dialects include `postgres`, `mysql`, and `tsql`. A statement that does not parse is refused. |

Do not add a third SQL generator. Do not keep a handwritten `CREATE TABLE` for each engine in a skill, a ticket, or a prompt.

## Render a table

1. Build the table as a SQLAlchemy `Table`: column name, a generic type (`BigInteger` for a count, `Numeric` for a decimal, `String`, `DateTime`, `Boolean`, `JSON`), nullability, and the primary key.
2. Compile it on the engine that will run it:

```python
from sqlalchemy.schema import CreateTable

str(CreateTable(table).compile(dialect=engine.dialect))
```

3. Run that string on that same engine, inside the migration command. Do not print a connection string.

The logical types from a data-profiling silver spec map onto those generic types before compilation. The compiler chooses `BIGINT` or `bigint`, `NVARCHAR` or `text`, `JSON` or `jsonb`. The skill does not list those spellings.

## Translate a statement

```python
import sqlglot

sqlglot.transpile(statement, read="postgres", write=dialect)[0]
```

`dialect` is `mysql` or `tsql`. If transpile raises, the statement is not portable. Stop. Do not repair it by editing the text.

These are not portable, and SQLGlot must not be asked to carry them:

- `LANGUAGE plpgsql` function bodies
- PostgreSQL `jsonb` operators and `jsonb_array_elements`
- `LATERAL`, `unnest(...) WITH ORDINALITY`, advisory locks, `pg_catalog` checks
- partial indexes, `GIN`, and `plan_cache_mode`

A store migration that is mostly those constructs stays on PostgreSQL until that behavior is rewritten as a SQLAlchemy model or as engine-specific code outside a skill. Copying the `.sql` file into MySQL or SQL Server is not a translation.

## Engines

| Connection scheme | SQLAlchemy dialect | SQLGlot write |
|---|---|---|
| `postgresql` | `postgresql` | `postgres` |
| `mysql` | `mysql` | `mysql` |
| `mssql` | `mssql` | `tsql` |

SQL Server Express uses the `mssql` dialect. The 10 GB limit is an edition limit, not a different SQL dialect.

## What this skill does not do

It does not apply MDM, RDM, Bookkeeping, Change Journal, or silver migrations. Data-operations applies those. It does not invent a statement the library cannot compile. It does not accept a license or print a password.
