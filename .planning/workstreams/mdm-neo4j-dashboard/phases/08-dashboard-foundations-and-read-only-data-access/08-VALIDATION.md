---
phase: 08
slug: dashboard-foundations-and-read-only-data-access
status: draft
nyquist_compliant: true
wave_0_complete: false
created: 2026-05-17
---

# Phase 08 - Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest via uv |
| **Config file** | `pyproject.toml` |
| **Quick run command** | `uv run pytest tests/mdm/test_dashboard_readonly.py tests/mdm/test_graph_readonly.py tests/architecture/test_dashboard_foundation_boundaries.py` |
| **Full suite command** | `uv run pytest tests/mdm tests/architecture` |
| **Estimated runtime** | ~60 seconds |

---

## Sampling Rate

- **After every task commit:** Run `uv run pytest tests/mdm/test_dashboard_readonly.py tests/mdm/test_graph_readonly.py tests/architecture/test_dashboard_foundation_boundaries.py`
- **After every plan wave:** Run `uv run pytest tests/mdm tests/architecture`
- **Before `$gsd-verify-work`:** Full suite must be green
- **Max feedback latency:** 60 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 08-01-01 | 01 | 1 | DASH-02 | T-08-01 | MDM helper performs bounded reads and never commits | unit | `uv run pytest tests/mdm/test_dashboard_readonly.py` | W0 | pending |
| 08-01-02 | 01 | 1 | DASH-03 | T-08-02 | Neo4j helper treats config as optional and runs only static read queries | unit | `uv run pytest tests/mdm/test_graph_readonly.py` | W0 | pending |
| 08-01-03 | 01 | 1 | ISO-02 | T-08-03 | Dashboard/helper modules do not import mutation pipeline or graph sync surfaces | architecture | `uv run pytest tests/architecture/test_dashboard_foundation_boundaries.py` | W0 | pending |
| 08-02-01 | 02 | 2 | DASH-01 | T-08-04 | Streamlit shell launches from documented uv command and uses approved placeholder/status copy | static/import | `uv run pytest tests/architecture/test_dashboard_foundation_boundaries.py` | W0 | pending |
| 08-02-02 | 02 | 2 | ISO-01 | - | Changed files stay in the dashboard worktree scope and avoid generated deployment artifacts | source review | `git status --short` | existing | pending |

---

## Wave 0 Requirements

- [ ] `tests/mdm/test_dashboard_readonly.py` - credential-free MDM read-only helper tests.
- [ ] `tests/mdm/test_graph_readonly.py` - fake-client Neo4j read-only helper tests.
- [ ] `tests/architecture/test_dashboard_foundation_boundaries.py` - static boundaries for dashboard scope and forbidden imports.

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Local Streamlit render check | DASH-01 | Streamlit browser rendering is outside existing automated test infrastructure | Run `MDM_DATABASE_URL="<local-or-dev-db-url>" uv run --extra dashboard --extra mdm-runtime streamlit run examples/mdm_graph_dashboard/streamlit_app.py` and confirm the Overview page shows MDM status, Neo4j optional status, Refresh data, and Phase 8 placeholders. |
| Secret redaction in live connection failures | DASH-02, DASH-03 | Live driver errors vary by database and network | Launch with intentionally invalid values and confirm UI messages mention env var names but do not print DSN, URI, username, password, or secret JSON values. |

---

## Validation Sign-Off

- [x] All planned implementation areas have an automated verify command or Wave 0 test dependency.
- [x] Sampling continuity: no 3 consecutive tasks without automated verify.
- [x] Wave 0 covers all missing test-file references.
- [x] No watch-mode flags.
- [x] Feedback latency < 60 seconds.
- [x] `nyquist_compliant: true` set in frontmatter.

**Approval:** pending
