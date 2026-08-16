# 03 — Route bootstrap-next's special-cased profile through the shared lookup

**What to build:** `bootstrap-next` currently hardcodes its own task profile
(`"medium"`) as a special case, independent of both `workflow_profile()` and
`write_warehouse_mdm_gold_definition`. Switch it to consult ticket 01's
shared mapping instead, so all three original mechanisms collapse onto one
source of truth. This is a different call site from ticket 02 and can be
done in parallel with it.

**Blocked by:** 01

**Status:** ready-for-agent

- [ ] `bootstrap-next`'s task profile resolution reads from the shared
      mapping instead of its own hardcoded `"medium"` special case
- [ ] `bootstrap-next`'s resolved profile is unchanged from today's behavior
      (this ticket is a pure migration, not a profile change)
