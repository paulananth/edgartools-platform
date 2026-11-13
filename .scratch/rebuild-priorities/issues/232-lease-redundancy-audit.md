# 232: Are the Bookkeeping step leases redundant with the destinations they protect?

Type: task. Status: open (audit complete; three changes proposed below).

## Question

Every step of every load target takes a lease on named resources before it does any work
(`edgar_warehouse/rules/shape.py`). The destinations each step writes already have their own
protection: an immutable artifact store, a store-wide merge lock, a silver table lock and a
primary key, a Change Journal unique key and an immutable trigger. Which leases still earn their
keep, and which are a second copy of a protection the destination already has?

## Checklist

- [x] Inventory every step's lease scope and the database/destination protection that already exists for that operation (2026-11-13 ET)
- [x] Trace each operation's claim, report, destination mutation and completion authority path (2026-11-13 ET)
- [x] Evaluate each case against the seven wastes, including whether leases remain necessary for recovery and fencing (2026-11-13 ET)
- [x] Check the implementation history and the tests for the reason leases were introduced (2026-11-13 ET)
- [x] Write the recommendation with verification evidence (2026-11-13 ET)
- [ ] Part 1: remove the artifact-scope lease from the steps whose output the artifact store already protects (branch and PR)
- [ ] Part 2: give a snapshot silver table one table-scoped lease instead of one lease per landing unit (branch and PR)
- [ ] Part 3: either wire the destination guard into the merge and landing transactions, or delete the unreachable guard path (decision, then branch and PR)

## 1. What each operation leases, and what already protects it

Step shapes come from one table, `edgar_warehouse/rules/shape.py:17-33`. Every target in
`rules/sources/*/source.yaml` and `rules/pipelines/*/pipeline.yaml` is expanded through it, so the
inventory below is the whole repository (read with `shape.expand_source`, 14 rule files, 20 targets).

| Operation | Lease scope | Destination protection that already exists | Verdict |
| --- | --- | --- | --- |
| `artifact.copy` | `artifact:{destination}` | `Artifacts.put_bytes` never overwrites: a different byte at the same URI fails the work, the same bytes reconcile (`edgar_warehouse/bookkeeping/clean/artifacts.py:173-207`) | remove |
| `source.read` | `artifact:{destination}` | same immutable artifact store; the read output is a deterministic function of the frozen input | remove |
| `source.combine` | `artifact:{destination}` | same immutable artifact store | remove |
| `mdm.prepare` | `artifact:{destination}` | same immutable artifact store; the manifest is a deterministic function of the frozen reading | remove |
| `mastering.merge` | `mdm:consumer:{consumer}` | `mastering_lock` row held `FOR UPDATE` for the whole merge, one writer at a time (`edgar_warehouse/mastering/store.py:56-60`, taken in `mastering/merge.py:115`); `mastering_file` makes a file's merge idempotent by its own key (`mastering/store.py:62-63`, `merge.py:116-118`) | keep (see §4) |
| `silver.land` | `silver:{silver}:{unit}` | `LOCK TABLE ... IN SHARE ROW EXCLUSIVE` for the merge of the staged rows only, and `PRIMARY KEY` on the spec's key (`edgar_warehouse/silver_writer/relational.py:18-33,74-100`; `silver_writer/database.py:99`) | keep, but **scope is wrong for snapshot tables** (§3) |
| `silver.derive` | `silver:{silver}`, `silver:{reads}` | none: a derive rebuilds its whole table and a snapshot delivery deletes every row the delivery lacks | keep |
| `journal.record` | `artifact:{destination}` | the Change Journal's own `UNIQUE (producer, event_key)` and its immutable-event trigger; a content conflict raises `JournalConflict` and the worker settles each file singly (`edgar_warehouse/change_journal/migrations/schema.sql:159-161`, `workers/journal_record.py:73-83`) | remove |
| `provider.capture` | `provider:sec`, `output:{destination}` | none: an HTTP request to a provider is an external effect with no atomic destination to protect it | keep |

Two of these were already narrowed once: source read and combine run locally and take no lease at
all (ticket 210, `edgar_warehouse/bookkeeping/clean/config.py:307-309`), and a landing unit leases
its own part of a table so a landing step's units land side by side (commit `6ab24e7a`).

## 2. Where the lease is actually enforced

The lease lives in one table, `bookkeeping.lease` (`resource` primary key, `token`, `run_id`,
`attempt`, `expires_at`), and one function, `bookkeeping.claim_unit`
(`edgar_warehouse/bookkeeping/clean/migrations/schema.sql:59-90`):

1. **Claim.** The worker calls `bookkeeping.claim`; the function locks the work item and each
   resource row `FOR UPDATE NOWAIT`, refuses a live lease on any resource, increments the token on
   takeover and returns the proof. Sorted resource order plus one transaction means a partially
   acquired set rolls back on contention.
2. **Renewal.** A renewal thread extends the expiry and rewrites the proof into the envelope the
   work holds (`edgar_warehouse/workers/__main__.py:36-78`).
3. **Report.** The worker's own check report is admitted only against the live attempt and the
   live lease (`edgar_warehouse/bookkeeping/clean/engine.py:407-462`).
4. **Completion authority.** `bookkeeping.finish` re-checks the proof inside the completion
   transaction and stores `authority_until` on the work item
   (`migrations/schema.sql:167-205`). Bookkeeping's own authority is real and stays.

**The destination guard is not on this path.** The spec for the original design says a destination
guard locks its resource rows inside the business transaction and a deferred check rejects expiry
at commit (`docs/specs/configured-bookkeeping.md`, "Lease acquisition sorts resources…"). The code
for that is installed by `bookkeeping init-guard`
(`edgar_warehouse/bookkeeping/clean/destinations.py:12-42`,
`migrations/destination_guard.sql`) and the helper `destinations.guard(conn, claim)` exists
(`destinations.py:45-53`) — but no production code calls it. A repository-wide search finds callers
only in tests. The other half of that path, `mdm.Store(engine, lease_authority=…)`
(`edgar_warehouse/mdm/store.py:490-503`) and `mdm.prepared.authority(store)`
(`edgar_warehouse/mdm/prepared.py:33-41`), has no caller either: nothing constructs a `Store` with
`lease_authority`. The comment in `workers/__main__.py:39-42` that says MDM fences its transaction
with `bookkeeping_guard` describes a path the current runtime does not take — the merge writes
through `mastering/store.py`, not through `Store.commit`.

So today a lease is enforced in Bookkeeping only. A stale worker can still write to a destination
after its lease has been taken over; what stops the damage is the destination's own protection,
which is why §1's "remove" cases are safe and why §4's "keep" cases are not.

## 3. One defect found: a snapshot table landed by several units loses rows

`silver.land` leases `silver:{silver}:{unit}`: each unit takes its own lease, so two units of the
same table hold different leases and run at the same time. That is safe for an `upsert` or `append`
table. It is not safe for a `snapshot` table: a snapshot delivery deletes every row the delivery
lacks (`edgar_warehouse/silver_writer/relational.py:96-98`), and each unit's delivery holds only
its own keys. Two units of one snapshot table therefore delete each other's rows, in whichever
order they commit, and the table ends up holding one unit's rows.

The silver table lock does not prevent this: it serialises the two merge phases, and the deletion
is inside the merge phase. The correct scope for a snapshot table is one lease for the whole
table, `silver:{silver}`, the way `silver.derive` already takes it.

Whether any registered table is a snapshot landed by more than one unit today was not checked in
this audit; the fix is the same either way, and the change is a one-line scope change in
`rules/shape.py` keyed by the table's registered load mode.

## 4. The seven wastes, case by case

| Waste | What the lease costs today | What it buys |
| --- | --- | --- |
| Waiting | A claim on a held resource waits for the retry policy's backoff and then leaves the unit waiting (`engine.py:191-215`); a lost lease stops the work outright after the renewal thread sees "Stale lease" | Nothing extra on the artifact steps: the artifact store already refuses a conflicting write |
| Motion | Every unit of every step pays a claim, a heartbeat thread, and a renewal round trip to the control store; the GLEIF load lost its lease twice this way and once ran 2 h 8 min past the loss (ticket 231 checklist, 2026-11-13 01:07 ET) | The merge, derive, landing and capture cases need *some* exclusion; a lease is the only one that spans a step's whole work |
| Over-processing | The artifact-scope lease is taken for every unit of every reading step, to exclude a second worker from writing an output path that is already unique to that unit | Nothing: the output path is per unit and the store refuses to overwrite it |
| Over-production | The guard schema, the `init-guard` command, `destinations.guard`, `Store.lease_authority` and `prepared.authority` exist for a destination-fenced transaction that no worker performs | Nothing today; it is either wired or deleted (§3 of the checklist) |
| Defects | A lease that expires mid-work produces a report Bookkeeping refuses ("Stale lease"), after the destination write has already happened; the two stores are separate databases, so the refusal is a late, confusing failure | The merge and landing cases still need their exclusion, but from the destination's own lock, not from a late refusal |
| Transport, Inventory | no lease-specific cost | — |

## 5. History: why the leases were introduced

- `155fb8ef` ("Add fresh configured Bookkeeping core and Rules integration", #732) introduced the
  lease table, the claim function, the destination guard and the deferred expiry check together.
  The spec it carried states the design: leases for the resources a step actually conflicts on,
  a destination guard that locks those resources inside the business transaction, a deferred check
  that rejects expiry at commit, and Bookkeeping's own deferred authority check on completion
  (`docs/specs/configured-bookkeeping.md`). Mutual exclusion and safe recovery after a worker
  dies were the point.
- `ab3a78ec0` (ticket 210) took source read and combine out of Bookkeeping entirely; they take no
  lease, no claim and no verifier.
- `8cf2afdac` (ticket 231, #1721) put every target on one shape, with the leases following from
  what a step does.
- `afa7bae92` (#1726) fixed renewal: a dropped connection no longer ends the renewal for good, and
  a lease Bookkeeping refuses stops the work at once.
- `6ab24e7a` (#1735) narrowed the landing lease to the unit, so a landing step's units land side
  by side.
- Ticket 231's run-checks part explicitly kept "leases and fencing" when the verifier duty went.

The original reason still holds for the four operations in §1 marked keep. It does not hold for the
five artifact-scope leases, and the guard half of the original design is currently unreachable.

## 6. Recommendation

| Lease scope | Action |
| --- | --- |
| `artifact:{destination}` on `artifact.copy`, `source.read`, `source.combine`, `mdm.prepare`, `journal.record` | **Remove.** The artifact store and the Change Journal already refuse a conflicting write; the scope excludes a second worker from a path only that worker owns. Change: drop the scope from `rules/shape.py`, keep the `leases` list non-empty by construction (the work-unit key remains the identity). |
| `silver:{silver}:{unit}` on `silver.land` | **Keep, and re-scope**: one lease for the whole table when the table is a snapshot, per unit otherwise. |
| `silver:{silver}`, `silver:{reads}` on `silver.derive` | **Keep.** A derive rebuilds its whole table; nothing in silver excludes a second rebuild. |
| `mdm:consumer:{consumer}` on `mastering.merge` | **Keep.** The merge's store-wide lock serialises the writes but does not stop two runs from merging the same consumer's batch and publishing twice; the file-level idempotency covers a retry, not two concurrent runs. |
| `provider:sec`, `output:{destination}` on `provider.capture` | **Keep.** An HTTP request to a provider has no atomic destination to protect it. |
| The destination guard (`bookkeeping_guard.authorize`, `Store.lease_authority`, `prepared.authority`, `bookkeeping init-guard`) | **Decide:** wire it into the merge and landing transactions, where a stale worker can still write, or delete it. Today it is installed and unreachable. |

Removing the five artifact-scope leases does not remove the `bookkeeping.lease` table or the
authority checks: the merge, landing, derive and capture leases stay, and Bookkeeping's completion
authority check is unchanged. The control store's five-table shape is asserted by
`tests/integration/test_configured_bookkeeping_postgres.py:141-149`.

## Verification evidence

- Step and lease inventory: every target in `rules/sources/*/source.yaml` and
  `rules/pipelines/*/pipeline.yaml` expanded through `edgar_warehouse.rules.shape.expand_source`
  (14 files, 20 targets); the lease scope of each operation is the one table in §1.
- Claim, report and completion paths read in `edgar_warehouse/bookkeeping/clean/engine.py:191-215,
  369-473` and `migrations/schema.sql:12-36, 59-90, 167-205`.
- The destination guard has no production caller: repository-wide search for `destinations.guard`,
  `bookkeeping_guard.authorize`, `lease_authority=` finds only `destinations.py`, `cli.py` and
  tests.
- `tests/integration/test_configured_bookkeeping_postgres.py`: 56 passed (the whole file, 50.88 s),
  of which the lease cases (contention, multi-resource rollback, expiry, renewal and stale
  completion) are 7 passed.
- `tests/unit/test_configured_bookkeeping_contract.py -k invalid_configuration`: 13 passed.
- History read from `git show 155fb8ef`, `ab3a78ec0`, `8cf2afdac`, `afa7bae92`, `6ab24e7a`,
  `fd26a27f` and the ticket 231 checklist.
