# 02 — Skip and network metrics on existing capture path

**What to build:** A command re-run over already-loaded scope reports how much work was **network** vs **silver skip** (extending existing network_fetches style metrics), so operators can prove “we did not reload SEC” instead of guessing from wall-clock time.

**Blocked by:** None — can start immediately (can run in parallel with 01).

**Status:** resolved

- [x] Capture-related runs emit comparable counts for real SEC/edgartools network work vs skips due to existing silver work
- [x] A documented way exists to observe these counts (logs, run summary, or command output)
- [x] Re-run of a fully loaded scope shows high skips and low network on the happy path
- [x] Tests cover at least one path where skip is asserted and network is not invoked

