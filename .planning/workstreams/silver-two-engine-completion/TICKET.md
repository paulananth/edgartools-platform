# Complete Silver on PostgreSQL and MySQL

Status: supported two-engine remainder implemented and locally qualified; publishing the PR. Calendar intervals are deferred; CI remains pending.
Parent: [Two-engine priority](../platform-three-databases/01-migrate.md).
Branch: `codex/silver-two-engine-completion-20261029`, based on `f5f02a7d2`.

## Parts

- [x] Reconcile existing registration, types, delivery, quality, master-link and installed-caller evidence — 2026-10-29 21:19 ET: current normal MdmIds and installed ids/silver scenario already qualify real links; shared delivery/owner suites retained. Concrete gaps: MySQL partition indexes and exact JSON decimal file/readback transport.
- [x] Qualify owner-only installation, interrupted registration recovery, configured indexes and runtime permissions on MySQL — 2026-10-29 21:19 ET: 37 selected real-engine cases passed in 20.71 seconds, including interrupted index CREATE, populated index repair, metadata/runtime DDL refusals and existing migration recovery.
- [x] Complete elapsed-duration text, exact decimal/JSON transport and configured partition indexes without changing historical migrations — 2026-10-29 21:19 ET: PostgreSQL 26 cases passed in 11.16 seconds; MySQL 37 passed; JSON Lines regression first failed on lost digits, then passed; decimal scale is checked independently of the Python arithmetic context.
- [ ] ~~Add exact calendar-month/year interval storage and populated-table conversion~~ deferred to [Calendar intervals](CALENDAR-INTERVALS.md): operator explicitly deferred this scope; MySQL refuses it atomically.
- [x] Account for actual configured MDM master links and refresh on PostgreSQL and MySQL — 2026-10-29 21:19 ET: carry forward unchanged normal-reader/land/late-master/merge/reversal/refresh/replay evidence from #1210/#1212, tests/installed_workflow/test_mdm_workflow.py ids/silver and tests/storage_adapters/master_id_scenarios.py. Both configured kinds and engines retain the installed scenario; no duplicate test added.
- [x] Qualify append/upsert/snapshot, quality, rollback, replay and populated registration through the normal callers on both engines — 2026-10-29 21:19 ET: retained shared suite plus the new exact-type/index cases passed on both engines. Installed committed-head proof remains below.
- [x] Qualify the committed revision outside the checkout — 2026-10-29 21:35 ET: dfb0028a independently installed all five wheels; three normal CLI/typed readback cases passed per engine (append/upsert/snapshot): MySQL 183.92 seconds and PostgreSQL 42.53 seconds.
- [ ] Verify required CI on the published head; this remains the merge gate.
- [x] Review Standards, Spec and GoF and reconcile parent records against verified results — 2026-10-29 21:35 ET: review below and parent checkpoint preserve the calendar deferral, SQL Server gate and CI limit.
- [ ] Publish the implementation PR and verify its published head.
- [x] Learning → skill — 2026-10-29 21:35 ET: separate PR #1229, head da7eb5ce, corrects data-operations support claims and adds “Qualify Silver storage”; 87 genericity checks and skill validator pass. Skill PR is ready; CI remains its merge gate.

## Boundaries

Configuration owns source/kind policy, columns, types, keys, links and checks.
Shared Rust/Python prepares behavior; databases retain durable atomic storage,
permissions, constraints, locking and recovery. Reuse the typed DatabaseSink and
normal migration/registration/CLI interfaces; no parallel sink or migration
framework. SQL Server, hosted cutover, source activation and provider requests
remain outside this two-engine ticket. Never alter shared operational Silver.
Disruptive tests use disposable isolated databases and restricted test roles.

## Initial review

Existing code/history already provides a single DatabaseSink and selected-engine
owner adapter. The GoF reviewer method finds no justification for a new class
hierarchy. Current MdmIds uses the governed selected-engine record reader; its
old PostgreSQL-only inventory is stale, but end-to-end Silver link evidence is
is already provided by the retained installed ids/silver family. MySQL registration lacks the partition index that PostgreSQL
creates. INTERVAL transport currently accepts Python timedelta only, while its
logical spec also admits interval text; qualify the required exact semantics
before choosing a representation or changing code.

## Verification and limits

Affected unit cohorts: 28 passed after the JSON parser correction; the subsequent
expanded Silver unit/schema/retirement cohort passed 15, with 26 correctly
unaffected cases deselected by testmon. Each invocation stayed below five minutes.
Local native dependency setup took 4 minutes 19 seconds. The first database
attempt used stale private port metadata and failed before any test database was
created; retry resolved the actual existing test-container bindings without
changing or restarting those servers. Isolated databases and generated roles are
removed by the existing fixture after each cohort.

Calendar interval storage remains incomplete by explicit operator decision.
PostgreSQL's existing other interval forms remain available; portable day/time
text is normalized exactly to elapsed microseconds. MySQL refuses calendar forms
rather than interpreting a month as a fixed number of days. Source activation,
SQL Server qualification and hosted changes remain outside this ticket.

## Review

### Standards

Fresh Codex branch/worktree; only invented test rows, private connection handling
and disposable databases. Existing containers, operational stores and historical
migrations remain unchanged. Local testmon caches are worktree-specific. The
prospective and actual overlap guards passed for the implementation paths.

### Spec

One shared sink remains authoritative. Configuration supplies fields, types,
partition columns, modes and links. MySQL's owner installs/repairs a derived
partition index without changing a registered spec or rows. Runtime cannot
perform that DDL. JSON decimal digits survive file reading, binding and readback;
returned fractional JSON numbers are Decimal values rather than rounded floats.
Elapsed text uses exact microseconds; calendar support remains explicitly deferred.

### GoF

Reviewed existing sink/type/owner history and the available reviewer smell
catalog before and after the change. Keep the existing Sink facade and storage
adapter. Small transport functions and the existing TypeDecorator boundary handle
the demonstrated differences; a new sink, class hierarchy or migration framework
would add indirection without reducing a repeated change cost. The liability of
exact JSON readback is a raw-text cast and Decimal-valued fractional results;
real-engine round-trip/replay tests cover the boundary. Committed installed proof
and CI are still required before final qualification.

The first committed installed-caller attempt exceeded 280 seconds during native
package preparation; no installed behavior pass is claimed from it. Its owned
processes stopped. Reuse the checkout's existing native target cache on retry;
retain the same local test deadline. Exact JSON parsing also keeps the prior
integral numeric master-key spelling through a bounded Decimal normalization.

## Installed qualification — 2026-10-29 21:35 ET

Both engines passed the committed five-wheel caller from dfb0028a, outside the
checkout, with three modes and exact decimal/nested JSON/elapsed-duration readback
and configured index verification. MySQL reused the native target cache and
passed within the unchanged 280-second deadline; PostgreSQL reused the built
wheel cache. All disposable databases/roles were cleaned by the fixture.
The following record changes leave the tested runtime and test bytes unchanged.

The authorized supported-type work is implemented; overall Silver completion
still excludes the explicitly deferred calendar capability. Required PR CI and
publication are still pending until recorded by their actual outcomes.
