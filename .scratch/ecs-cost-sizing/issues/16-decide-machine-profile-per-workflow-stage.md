# Decide the Machine Profile for Every Workflow Stage

Type: grilling
Status: resolved
Blocked by: 03, 06, 12, 13

## Question

Which warehouse or MDM `small`, `medium`, or `large` profile should each
retained workflow stage use after accounting for historical peak and sustained
CPU/memory, records per item, concurrency, duration, failure/OOM history, and
cost and time per successful output?

Retain separate warehouse and MDM runtime families unless the profile-family
decision says otherwise, but use one sizing vocabulary and one canonical
selection contract. Do not infer a downgrade from a sparse family-level
average. Require execution-level evidence for the actual workload class and
preserve documented memory floors for gold and residual-holds/security work.
Where two profiles are correct and stable, prefer the one that materially
shortens end-to-end completion on the accepted cost frontier; do not downsize
solely because the smaller profile is cheaper.

The full-canonical SeedUniverse stage is already fixed at warehouse `large`
after a live 4-GiB OOM; the dormant batched workflow's medium reference has no
production execution evidence and is not counterevidence. This decision may
refine bounded seed and parsing utilities, but it cannot lower
`warehouse.full_canonical_seed` without a new three-canary high-risk evidence
cohort. Keep `mdm-large` operational until the accepted representative,
non-zero-data `mdm-medium` canaries pass; after acceptance, its normal binding,
registration, bake protection, rollback, and emergency-use rules follow
**Decide Warehouse Versus MDM Profile Families**.

## Answer

Closed the open canary/evidence gaps Tickets 03/06/09 deliberately left
pending, plus one new class this ticket's own evidence surfaced. Four
decisions:

**1. `mdm.full`'s "current-digest full run" requirement — flagged, not
closed.** The only current-generation-memory (4 GiB, `mdm-medium:138`)
evidence for a full-universe `mdm run` is one execution (81% peak memory,
12h17m, succeeded) reused across Ticket 02 and Ticket 13. Leaning toward
treating this as satisfying Ticket 03's requirement — 81% is comfortably
under the 85% constrained threshold and the memory generation matches — but
without independent confirmation this ran under the *currently deployed*
image (not just current memory tier on a possibly-older revision), this
stays a flagged, provisional close rather than a fully verified one.

**2. Two standing downgrade canaries, unscheduled until now.**
`mdm.residual_security`→`mdm-medium` (needs 3 non-zero-data canaries, 0
done) and `warehouse.gold_standalone`→medium (needs 2, 0 done — the one
execution on record is the same large-profile baseline reused twice, not a
canary). **Neither's operational tier changes** — both remain at their
`large` safety floor per Ticket 03/09's existing policy. Scheduled as
follow-up work: see Ticket 25 (residual_security canaries) and Ticket 26
(gold_standalone canaries).

**3. New workload class: unbounded `mdm sync-graph`.** Ticket 15 decided
to raise `--mdm-graph-limit` to 0 for production and explicitly folded its
required canary into this ticket. No class in Ticket 06's matrix was sized
for this — every `sync-graph` execution on record ran at smoke-test scale
(100–200 items) on `mdm-medium`. At real ~193K-node scale, duration/memory
are completely unmeasured. **Decision: the first unbounded canary runs on
`mdm-large`**, not the untested assumption that `mdm-medium` scales
linearly from 200 items to 193K — matches how this codebase has previously
handled genuinely new, unmeasured workload shapes (`residual_security`'s
own history: prove safe on the larger profile before considering a
downsize, not the reverse). Folded into Ticket 25 as the same canary
cohort, since both are MDM-runtime canaries currently blocked on the same
kind of evidence gap.

**4. `warehouse.full_canonical_seed` retired as a separate class.** PR
#396 folded `Stage0CompanyIdentity` into `WindowedBootstrap`, which Ticket
13 confirms already runs entirely on `large` throughout. The old class's
safety floor moved with the code rather than lapsing — no separate class is
needed going forward; this stage is now just part of
`warehouse.combined_full_pipeline`.

**Everything else in Ticket 06's initial 10-class matrix stands
unchanged** — no further stage required splitting or reclassification
beyond the four items above. Ticket 14's retirements (13 machines) don't
remove any workload class from this matrix, since every retained workflow
that needs a given class (e.g. `bronze_seed_silver_gold` for `mdm.full`)
already covers it; retirement only removes redundant registrations, not
classes.
