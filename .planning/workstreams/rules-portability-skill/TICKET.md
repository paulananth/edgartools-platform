# Preserve the Rules storage qualification lessons

Status: guidance, local review and implementation CI qualified; current published head must pass CI before readiness/merge.
Base: 2633024fc; branch codex/rules-portability-skill-20261029.
Implementation: PR #1235; guidance does not claim that pending CI is complete.

- [x] Add the demonstrated Rules-to-mastering handoff, exact approval-evidence and completed-DDL readback lessons to the existing storage reference — 2026-10-29 23:49 ET: independent Spec review confirmed the bounded lessons; no deployment authority added.
- [x] Verify source neutrality, links and whitespace with the affected checks — 2026-10-29 23:49 ET: 87 genericity cases passed, whitespace and ownership guard passed; independent Standards/GoF review found no issue. No links were added.
- [x] Publish the guidance in its own PR and qualify CI before readiness — 2026-10-30 00:28 ET: PR #1236, all 20 checks passed on guidance head 800720cf. This closeout changes the ticket only; require its published head to pass CI before marking ready again. Land after implementation PR #1235.
- [x] Learning → skill: mdm-engineering/references/storage-adapters.md, Rules handoff qualification — 2026-10-29 23:49 ET: normal caller traversal, unchanged registration reuse, target-specific proof evidence and guard/index readback.
