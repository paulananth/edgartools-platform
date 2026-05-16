# Phase 1: Failure Surfacing — Discussion Log

**Date:** 2026-05-15
**Areas discussed:** Tolerance threshold, Partial success policy, Verification approach

---

## Area 1: Tolerance threshold

**Q: What should replace ToleratedFailurePercentage: 10?**
Options: Set to 0 / Keep 10% with explicit check after / Make it a deploy-time variable
**Selected:** Set to 0 (strict, matches requirement exactly)

**Q: Keep 2 retries or increase to 3?**
Options: Keep 2 retries / Increase to 3 / You decide
**Selected:** Increase to 3 retries (one extra attempt before propagating failure)

---

## Area 2: Partial success policy

**Q: When bootstrap_phased fails mid-batch, what's the recovery path?**
Options: Re-run from scratch / Re-run only failed batches / Continue MDM/gold despite failure
**Selected:** Re-run only the failed batches (via targeted_resync after identifying failed children)

**Q: Does failed-batch recovery need automation or just a runbook?**
Options: Documented operator workflow / Script to extract + re-trigger
**Selected:** Documented operator workflow (new section in docs/runbook.md)

**Q: Where should the recovery runbook go?**
Options: docs/runbook.md / New docs/pipeline-recovery.md
**Selected:** Add section to docs/runbook.md (keep procedures centralized)

---

## Area 3: Verification approach

**Q: How to verify the fix works?**
Options: Definition diff + deliberate failure / Definition diff only / Full 100-company run
**Selected:** Definition diff + inject a deliberate failure

**Q: How to inject the deliberate failure?**
Options: Invalid CIK in batch input / Temporary tolerance override test / Kill ECS task manually
**Selected:** Invalid CIK (CIK 9999999 — clean, no production side-effects)

**Q: Should the test be scripted or manual?**
Options: Scripted test in scripts/ops/ / Manual operator check
**Selected:** Scripted test in scripts/ops/test-failure-surfacing.sh (repeatable regression check)

---

## Deferred Ideas

- Batch log correlation improvements (out of scope — Phase 2 or future)
- Automation for failed-batch CIK extraction and targeted_resync re-trigger (operator runbook sufficient for Phase 1)
