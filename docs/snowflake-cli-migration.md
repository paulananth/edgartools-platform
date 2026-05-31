# Snowflake CLI Migration & SQL Execution Best Practices

**Status**: Active &middot; **Scope**: `scripts/verify-pr1/` and any future helper scripts that apply Snowflake DDL/DML from `.sql` files.

This document captures the migration from legacy `snowsql` to the modern `snow` CLI, the eventual switch to the Python connector for files containing Snowflake Scripting blocks, and the SQL-tokenizer requirements that fall out of both.

The motivating bug:

```
── Stage 3 — Snowflake DDL deployment ──
[verify-pr1 FATAL] required command not found: snowsql
[verify-pr1] ✗ Stage 3 — Snowflake DDL deployment — FAILED (subsequent stages skipped)
```

Future-you: if you are tempted to reach for `snowsql`, **don't**. Read this first.

---

## 1. `snowsql` is deprecated. Use `snow`.

`snowsql` is the legacy Snowflake CLI (Java-based, separate installer, not maintained on the same cadence as the Python connector). It is **not** installed in this repo's CI environments and is not on most developers' machines. Anything that hard-required `snowsql` failed at the first line.

The modern Snowflake CLI is `snow` (Python-based, distributed as `snowflake-cli-labs`). It is what `infra/scripts/deploy-snowflake-stack.sh` and `scripts/test/smoke-test-single-cik.sh` already use.

### Install / configure

```bash
pip install snowflake-cli-labs       # or: uv pip install snowflake-cli-labs
snow connection add                   # interactive — writes ~/Library/Application Support/snowflake/config.toml on macOS
snow connection list                  # confirm name; export SNOW_CONNECTION=<name>
```

### Config file location varies by OS

The `snow` CLI does **not** read `~/.snowflake/connections.toml`. The canonical paths (in search order) are:

| Platform   | Path                                                       |
|------------|------------------------------------------------------------|
| Override   | `$SNOWFLAKE_HOME/config.toml`                              |
| macOS      | `~/Library/Application Support/snowflake/config.toml`      |
| Linux      | `~/.snowflake/config.toml` (fallback)                      |
| XDG        | `~/.config/snowflake/config.toml` (fallback)               |

Any helper that reads `snow`'s config file must check all four — this is what `snow_sql_file()` in `scripts/verify-pr1/00_lib.sh` does.

### Config format

```toml
[connections.edgartools-dev]
account = "..."
user = "..."
password = "..."           # or use authenticator / key-pair
warehouse = "..."
role = "..."
database = "EDGARTOOLS_DEV"
schema = "EDGARTOOLS_SOURCE"
```

---

## 2. Even with `snow`, **single-statement query mode breaks on Scripting blocks**

`snow sql --filename foo.sql` and `snow sql --query "..."` split input on `;` with a parser that does **not** respect:

- Snowflake Scripting `BEGIN ... END;` blocks (the internal `;` ends the EXECUTE IMMEDIATE prematurely).
- Dollar-quoted strings (`$$...$$` and `$tag$...$tag$`).
- SQL block comments containing `;`.

The bootstrap files in `infra/snowflake/sql/bootstrap/` use all three. So `snow sql --filename` will silently corrupt them.

### Fallback: drive the Python connector directly

`scripts/verify-pr1/00_lib.sh` :: `snow_sql_file()` reads the same `config.toml` `snow` uses, opens a `snowflake.connector` session, and applies one tokenized statement per `cur.execute()`. The connector accepts anonymous Scripting blocks (`BEGIN ... END;`) as a single statement — the server-side parser handles them correctly.

```bash
snow_sql_file infra/snowflake/sql/bootstrap/01_source_stage.sql
```

No new auth setup: the helper reuses whatever `snow connection list` shows.

---

## 3. The anti-pattern: do **not** wrap `BEGIN..END` in `EXECUTE IMMEDIATE $$...$$`

It is tempting to "fix" the splitting problem by rewriting

```sql
BEGIN
  EXECUTE IMMEDIATE 'CREATE STORAGE INTEGRATION ' || $storage_integration_name || ...;
END;
```

into

```sql
EXECUTE IMMEDIATE $$
  BEGIN
    EXECUTE IMMEDIATE 'CREATE STORAGE INTEGRATION ' || $storage_integration_name || ...;
  END;
$$;
```

This **looks** like it should work — `$$...$$` is a dollar-quoted string, the tokenizer respects it, the inner `;` is preserved. But it fails for a non-obvious reason:

> **Session variables (`$storage_integration_name`, `$storage_role_arn`, etc.) set via `SET var='...'` lines do not resolve inside an `EXECUTE IMMEDIATE` string literal.**

Snowflake treats the string as opaque text until evaluation time, by which point the parent session-variable binding is irrelevant to the literal text. Wrapping the block makes `$storage_integration_name` resolve as **literal characters**, not the configured value.

This bit us during PR-1 verification: a previous version of `snow_sql_file()` wrapped every top-level `BEGIN..END` block in `EXECUTE IMMEDIATE $verify_pr1$...$verify_pr1$;`. The wrap was syntactically valid, but the bootstrap deploys still failed because `STORAGE_AWS_ROLE_ARN = '$storage_role_arn'` ended up containing the literal string `$storage_role_arn`.

**Rule**: if the block references caller-supplied session variables, it must reach the server unwrapped.

The correct approach is to make the tokenizer **BEGIN/END-aware** — emit each top-level Scripting block as one atomic statement and let `cur.execute()` submit it unwrapped.

### 3a. Stricter parsing: parenthesize IF conditions

The modern snowflake-connector-python parser is stricter than legacy `snowsql` and requires **parentheses around `IF` conditions** in Scripting blocks:

```sql
-- ❌ Accepted by snowsql, rejected by snowflake-connector-python
IF COALESCE($var, '') <> '' THEN ...

-- ✓ Accepted by both
IF (COALESCE($var, '') <> '') THEN ...
```

The bare form raises `001003 (42000): syntax error ... unexpected 'COALESCE'`. Add parens to every `IF` condition in bootstrap SQL files that uses functions or operators.

---

## 4. SQL tokenizer requirements (the contract `snow_sql_file()` must meet)

When splitting a Snowflake `.sql` file into statements, the tokenizer must respect:

| State              | Opener         | Closer         | Notes                                                  |
|--------------------|----------------|----------------|--------------------------------------------------------|
| Line comment       | `--`           | newline        | Comment-only statements should be filtered out.        |
| Block comment      | `/*`           | `*/`           | May contain `;`, must not split.                       |
| Single-quoted str  | `'`            | `'`            | `''` is an escaped quote, not a close.                 |
| Dollar-quoted str  | `$$` or `$tag$`| matching       | May contain `;`. Tag preserves naming.                 |
| BEGIN..END block   | `BEGIN`        | bare `END;`    | **Track nesting depth.** Internal `;` does not split.  |

Critical distinctions inside a BEGIN block:

- `END;` (bare END followed by `;`) — closes a BEGIN block. Decrement depth.
- `END IF;`, `END LOOP;`, `END FOR;`, `END CASE;`, `END WHILE;`, `END REPEAT;` — close non-BEGIN constructs nested inside the block. **Do not** decrement BEGIN depth.

The tokenizer in `00_lib.sh` distinguishes these by peeking at the next non-whitespace character after `END`: if it's `;` (or EOF), it's a bare END.

---

## 5. Quick checklist for new helpers

If you are writing a new shell script that applies Snowflake SQL files:

- [ ] **Do not** require `snowsql`. Require `snow` (or skip CLI entirely and use the Python connector).
- [ ] If the file uses Scripting (`BEGIN..END;`, `EXECUTE IMMEDIATE`), use the Python connector path via `snow_sql_file()` from `scripts/verify-pr1/00_lib.sh`.
- [ ] If the file uses caller-supplied session variables (`$var` references after `SET var='...'`), do **not** wrap top-level blocks in `EXECUTE IMMEDIATE $$...$$` — wrap breaks session-variable resolution.
- [ ] Reuse the `snow_sql_file()` helper or a port of its tokenizer rather than calling `cur.execute_string()` directly — the latter naively splits on `;`.
- [ ] Reuse `snow`'s `config.toml`. Search the four canonical paths (see section 1) rather than hard-coding `~/.snowflake/`.

---

## 6. References

- `scripts/verify-pr1/00_lib.sh` :: `snow_sql_file()` — canonical helper, includes BEGIN/END-aware tokenizer
- `scripts/verify-pr1/03_check_snowflake_ddl.sh` — calls `snow_sql_file` for each bootstrap file
- `scripts/verify-pr1/README.md` — operator-facing run instructions
- `infra/snowflake/sql/bootstrap/01_source_stage.sql` — example file that exercises every tokenizer rule (3× plain `BEGIN..END;` blocks, 1× `BEGIN ... IF ... END IF; END;` nested block, 1× `BEGIN ... EXECUTE IMMEDIATE $$...$$ ... END;` block, plus 16 plain `CREATE TABLE` statements)
- Migration commits: `7d6cb87 fix(verify-pr1): swap snowsql -> snow CLI`
