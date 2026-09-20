# Define the exact transaction boundary between accepted decision, MDM projection, and checkpoint advancement

Type: grilling
Status: resolved
Blocked by: none (05 resolved)

## Question

The GoF review's Appendix C item 3: the exact transaction boundary between
accepted decision, current MDM projection, and checkpoint advancement.

Read against Clean MDM's `docs/specs/clean-mdm/recovery.md` ("Transaction
boundary" section, read-only on `origin/codex/clean-mdm-integration`), this
is already decided there for the MDM side: one Postgres transaction holds
the accepted decision, source assertions, identity/profile/relationship
projection, MDM Commit Evidence, Consumer Checkpoint, and every publication
intent — "no nested helper commits." Capture evidence precedes it in
`change_ledger`. Bookkeeping observes afterward; "do not claim a transaction
spans the three databases." Enforced by `mdm_v2.commit_batch` (migration
023): the application has no direct write privilege on any MDM table.

What Clean MDM's rule does not say is where ticket 05's publication
completeness check sits, since it reads `change_ledger` and cannot be inside
the MDM transaction.

## Comments

- 2026-09-19: operator asked "what two transaction" and "is the mdm commit
  records that a row is parsed, checked for already exists and inserted
  into pre merge table? explain what it checks." Clarified: parse, match
  ("already exists"), and decide all happen in Python *before* the commit;
  the commit is one call to `commit_batch`, which checks only write safety
  (bounded batch; same batch key ⇒ same result, different content ⇒ error;
  generation not stale; checkpoint expected and advancing; policy frozen;
  each assertion's dataset pinned and active at the right schema; assertion
  id not reused with different content; deferred records carry an open
  blocking review) and then writes everything in one commit. It does not
  check whether the match was right — that is why the candidate must be
  visible before the commit (pre-merge staging proposal). Operator: "order
  is fine, yes."

## Answer

**Two transactions, fixed order, nothing spans databases.**

1. **Capture** — database `change_ledger`. Source Capture verifies each
   file's hash and commits one Logical Source Revision row per file
   (manifest included). Durable evidence; no MDM table touched.
2. **Completeness precondition** — no transaction. Immediately before
   opening the MDM transaction, the consumer reads `change_ledger` and
   confirms the publication is complete per ticket 05 (manifest row
   present, every listed member has a verified row). Not complete ⇒ the
   MDM transaction does not open. Safe to check outside the transaction
   because `source_revision` rows are immutable: complete cannot become
   incomplete.
3. **Consume** — database `mdm`, Clean MDM's boundary adopted verbatim: one
   `commit_batch` call writes assertions, decisions, projection, MDM Commit
   Evidence, Consumer Checkpoint, and publication intents, or nothing. The
   checkpoint row records the publication consumed —
   `(source_family, source_native_revision)` — inside this transaction, so
   the MDM commit states exactly which publication it advanced past
   (this is the checkpoint-row content ticket 08's proposal carries).
4. **Bookkeeping** — `pipeline_run` status is updated afterward by
   observation of the committed batch and receipts, never inside 3.

The foundation spec cites Clean MDM's `recovery.md` for step 3 and adds only
step 2 and the checkpoint-row content in step 3. It does not define a
second commit path.
