# Superseded uncommitted work (2026-11-10)

The uncommitted changes from two long-lived worktrees, kept because each was
discarded after review found the work already in `main`.

Both branches are 200+ commits behind `main`, and every file was compared
against `main` before the working tree was reset. The patches apply cleanly
to their own branch base (`968dde63` for t149, `fe0afacf` for form4); they do
not apply to `main`, because `main` is ahead.

| Patch | Source branch | Base | State |
|---|---|---|---|
| `edgartools-platform-t149i-uncommitted.patch` | `claude/t149-ingest` | `968dde63` | superseded |
| `edgartools-platform-form4-*` | `claude/form4-security-issuer-title` | `fe0afacf` | superseded |

## t149 (`claude/t149-ingest`)

The Rust work landed: `crates/source-contract/src/context.rs`, `lib.rs`,
`text_transform.rs`, `tests/text_transform.rs`, `rules/source-sequence.yaml`
and `rules/sources/sec.registration/MAPPING.xlsx` are byte-identical to
`main`. `main` also holds a later fix to `html.rs` (the `shown` logic that
stops a unit stated for one statement from reaching the next), so the branch
copy would have regressed it.

Two items were not carried forward, deliberately:

- `rules/sources/sec.registration/silver-offering.yaml` declares a
  `price_range_ordered` check of kind `not_after` over `price_low` and
  `price_high`. `not_after` reads two columns of the same `DATE`, `TIMESTAMP`
  or `BIGINT` type; those columns are `DECIMAL(38,10)`. The real validator
  refuses it: *"not_after reads two columns of the same type, a date, timestamp
  or whole-number type, not price_low (DECIMAL(38,10)) and price_high
  (DECIMAL(38,10))"*. A date-order check over prices is also the wrong rule.
- `as_at: null` in the two silver specs is older than `main`'s
  `as_at: captured_at`, which uses the `zip_json` context that `main` gained.

The cell-position regexes in `registration-page.yaml` are an earlier,
less precise form of the patterns `main` now uses.

## form4 (`claude/form4-security-issuer-title`)

`edgar_warehouse/mdm/activation.py` and `rules/sources/sec.ownership/source.yaml`
are byte-identical to `main`. The rest differs only because `main` moved
on: `main` refactored `adapters.py` around `_named_values`, added the
`found-answers-only` rule versions, and carries newer proof evidence. The
`form4-security-issuer-symbol` rule, the `_issuer_symbol_id` adapter and
`EXACT_NAME_KEYS` are present in `main`, byte for byte, including the
operator's approval timestamp.

## Recovering

```bash
git checkout <branch-base>
git apply .scratch/superseded-uncommitted-20261110/<patch>
```

The branch tips are also kept as `archive/t149-ingest-20261110` and
`archive/form4-security-issuer-20261110`.
