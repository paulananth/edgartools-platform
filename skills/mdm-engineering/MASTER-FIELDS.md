# Designing the master store's fields

Read before adding a field to a master, a column or table to the mastering store, or a reader of the master. The rules
follow the [seven wastes](../data-platform/SKILL.md#the-seven-wastes): a field stored twice, read whole for one part, or
stamped on every value is transport and over-processing paid by every reader on every run.

## Measure before designing

Read what a stored master holds before deciding its shape: each top-level key, in how many masters, its average size, and
whether another table already holds it. Count only; print no value (a sample is enough: `tablesample system (1)`). Then name
each reader and the keys it uses. A design that skips this step guesses where the bytes are.

## Rules

1. **What a reader selects or joins by is a column.** A master's kind, status and surviving id (`canonical_id`) are read by
   the link build, the merge-survivor lookup and Gold for every master they touch. Kept only inside the stored text, each read
   decompresses and parses the whole master to find a few characters.
2. **What a master holds many of, with its own dates, is its own table.** A profile (a role a master holds from one date to
   another) is a row of `mastering_profile`, keyed by the master and the profile's id. Most masters hold none, so a reader
   that needs roles joins a small table, and a master without one stores nothing.
3. **Store a fact once.** The master's id is the row's key; its identifiers are rows of `mastering_identifier`; the records
   that make it are rows of `mastering_record`. None of them is repeated in the stored text. Where a table becomes the
   authority for a fact the text used to hold, the write keeps it exact: a value the master no longer holds is deleted, not
   left behind.
4. **A stamp that is the same for every value of a master is stored once for the master,** never on each value (the policy
   that decided the master, the version of its kind). Before moving one, check that no value can carry a different stamp.
5. **The stored text keeps what only it holds:** each field's value with its source attribution, what was cleared, what
   conflicts, and the details a source adds.
6. **One place splits and one place assembles.** The store's write splits a master into its columns, its rows and its text;
   its read of whole masters puts them back together, so a reader that needs the whole master never knows the split. A
   reader that needs only the columns reads only the columns.
7. **Prove the split loses nothing.** A test merges masters through every path (create, join, change, merge, alias) and
   asserts that the assembled master equals the one survivorship produced; a test of the reader that uses only columns fails
   if it reads the text.

## Schema changes

A new column or table is the owner's, made at the store's `init` (runtime code makes no table, temporary ones included).
Readers and writers change in the same pull request as the schema.
