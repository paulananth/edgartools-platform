# 06 — edgartools-only gateway for filing document capture (phase 1)

**What to build:** For filing documents/attachments, normal-mode SEC network capture goes through an edgartools-backed path only (no parallel raw client for that object class), with silver-once skip still winning before network. Strict_release mode continues to meet ticket 01 evidence rules.

**Blocked by:** 01 — Dual-mode capture contract; 03 — Silver-once skip for ownership.

**Status:** ready-for-agent

- [ ] Filing document capture for the migrated object class does not use a parallel non-edgartools download client
- [ ] Silver skip still prevents network when parse/capture completeness at version is satisfied
- [ ] Regression/architecture test fails if a forbidden parallel filing download path is reintroduced for that class
- [ ] Ticket 20-oriented strict_release path remains capable of evidence persistence
