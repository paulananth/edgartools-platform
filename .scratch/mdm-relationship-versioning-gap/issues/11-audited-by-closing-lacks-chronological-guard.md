Type: task
Status: resolved

## Question

`_derive_audited_by` (`edgar_warehouse/mdm/pipeline.py:4085-4101`) has its
own inline closing mechanism for a changed auditor: when `auditor_changed`
is true, it directly queries and closes every open AUDITED_BY version for
the company pointing at a *different* audit firm than the new row.

Unlike `_deactivate_if_properties_changed` (the shared helper IS_INSIDER/
EMPLOYED_BY use for the same "close on differing new value" concept,
Tickets 02/03 on this map), this inline copy has **no
`confirmed_chronologically_after` guard**. That guard exists specifically
because a late-filed amendment or a full-history resync/reconciliation
pass can revisit an OLDER row after a newer, already-correct version is
already open -- without the guard, reprocessing that older row would
incorrectly close the newer version using a stale date.

Fix this the same way Ticket 02 fixed it for IS_INSIDER: either add the
missing guard directly to `_derive_audited_by`'s inline query, or (likely
cleaner, and what `relationship-closing-pattern-framework`'s Ticket 02
assumes will happen) route AUDITED_BY through the existing
`_deactivate_if_properties_changed` helper instead of maintaining a
separate inline copy -- eliminating the duplication that let this bug
diverge from the already-fixed sibling in the first place.

This is a live, un-investigated bug (found while charting the
[relationship-closing-pattern-framework map](../relationship-closing-pattern-framework/map.md),
explicitly ruled out of that map's scope as a correctness fix rather than
a design question) -- not yet reproduced against real prod data or
confirmed to have actually caused a wrong closure in practice. Whoever
picks this up should confirm real impact (a live query for AUDITED_BY
rows closed by an out-of-order reprocessing event) before or alongside
the fix, per this repo's `/diagnosing-bugs` discipline.

## Answer

**Real impact confirmed live first, per `/diagnosing-bugs` discipline (not
skipped):** queried prod MDM Postgres directly -- `AUDITED_BY` currently
has **zero rows** in prod (`_derive_audited_by` has never actually
populated real data there yet). So this bug has caused no actual
corruption so far; it's a latent gap that would fire the first time this
derivation runs against real data with an out-of-order/restated row,
which is common enough (10-K/A restatements) to fix proactively rather
than wait for it to actually happen in prod.

**Design decision: added the guard directly to `_derive_audited_by`'s own
inline query (not routed through the shared `_deactivate_if_properties_changed`
helper), contrary to this ticket's own "likely cleaner" suggestion --
investigated and found that option isn't actually viable.**
`_deactivate_if_properties_changed`'s `current_by_pair` is keyed by
`(source_entity_id, target_entity_id)` -- it looks up and closes prior
versions for the SAME target, comparing PROPERTIES. AUDITED_BY's situation
is structurally different: the auditor CHANGE means the TARGET entity
itself changes (old audit firm -> new audit firm), so the correct lookup
is "every open version for this source entity pointing at a DIFFERENT
target" -- the shared helper's per-pair keying can't express this at all
(a lookup under the NEW target's key would find nothing, since the stale
row lives under the OLD target's key). Forcing AUDITED_BY through that
helper would require reshaping the helper's own keying model, a larger and
riskier change than this ticket asked for. Kept the existing inline query
shape, added only the missing guard.

**Reproduced live via a real regression test** (`/diagnosing-bugs`
discipline: found a genuine seam, not skipped) -- discovered the query's
own `ORDER BY (registrant_cik, audited_period_end, report_date,
accession_number)` sorts primarily by FISCAL PERIOD, not by real-world
filing time. A late-filed restatement for an EARLIER fiscal year (e.g.
FY2022, corrected auditor, filed 2024-06-01) sorts BEFORE a LATER fiscal
year's original filing (FY2023, filed 2024-01-15) in the same batch --
exactly the "older row processed after/interleaved with a newer version"
shape this guard protects against, and it's genuinely reachable within a
single `derive_relationships` call, not just across separate runs.
Reproduced against the unfixed code first: the missing guard let FY2023's
(chronologically EARLIER) processing attempt to close the restated
FY2022 version (chronologically LATER, `valid_from_date` 2024-06-01)
using FY2023's own earlier date (2024-01-15) -- this doesn't silently
corrupt data, it crashes with
`sqlalchemy.exc.IntegrityError: CHECK constraint failed:
ck_rel_instance_valid_interval` (Postgres's own `valid_to_date >
valid_from_date` constraint), since 2024-01-15 is not after 2024-06-01.
Confirmed the fix (guarding with `confirmed_chronologically_after`) makes
this a clean skip instead of a crash -- the restated version stays open,
matching `_deactivate_if_properties_changed`'s "when in doubt, leave it
open" philosophy exactly.

**Fix:** one guard clause added inside the existing
`for prior_version in prior_versions:` loop in `_derive_audited_by`
(`edgar_warehouse/mdm/pipeline.py`) -- `confirmed_chronologically_after(effective_from,
prior_version.valid_from_date)`, skipping the close when not confirmed.
No other behavior changed.

Tests: 1 new regression test in `tests/mdm/test_pipeline_relationships.py`
(`test_audited_by_late_restatement_does_not_close_newer_version_with_stale_date`),
reproduced the crash against unfixed code first, confirmed it passes
after the fix. Full `tests/mdm/audit*` + AUDITED_BY suite green (6
passed), full `tests/mdm/` suite green, full repo suite green.

This also resolves `relationship-closing-pattern-framework`'s ADR 0008
caveat that flagged `AUDITED_BY` as registered under its intended
pattern "despite" this bug.

3-axis `/code-review` (Standards/Spec/GoF), per CLAUDE.md hard rule, all
clean -- Standards caught one real, actionable finding: the
already-merged `RELATIONSHIP_CLOSING_PATTERNS` registry comment in
`pipeline.py` and ADR 0008's own Consequences bullet both described this
gap in present tense ("still missing... despite its inline closer...")
-- now stale now that the fix has landed. Fixed both to past tense,
pointing at this ticket as the resolution rather than an open caveat.
Spec review independently traced the new test's three-row batch by hand
against `confirmed_chronologically_after`'s real signature and confirmed
it genuinely exercises the described `ORDER BY` reproduction, not a
synthetic shortcut. GoF review independently re-verified (not just
trusted) the "don't force AUDITED_BY through the shared helper" call --
confirmed `_deactivate_if_properties_changed`'s dict keying structurally
cannot express AUDITED_BY's "any other target" lookup, and confirmed the
one real shared primitive (`confirmed_chronologically_after` itself) is
already factored out; only ~5 lines of loop scaffolding remain
duplicated across the two closers, not worth extracting at 2 call sites.

Full repo suite green: 3187 passed (up from 3186), 7 skipped, exit 0.
