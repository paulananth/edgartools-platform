# Bookkeeping without loader dependencies

Owner: Codex. Status: in progress. Claude has no assignment.
Branch: `codex/bookkeeping-loader-independent-design-20261002`.
Base: `417147e8` (main, PR #784; fetched 2026-10-02 10:47 ET).

## Request

Design Bookkeeping without any loader dependency. Correct the prior explanation:
the coupling is created by Bookkeeping's integration, not by the Company parser.
Codex owns this work; assign Claude work only on an explicit operator instruction.

## Checklist

- [x] Create a dedicated Codex branch/worktree and inspect current control interfaces — clean branch from fetched main, callback/registry/runner and source branches read; 2026-10-02 10:47 ET.
- [x] Record a loader-independent task protocol, authority ownership and failure/recovery behavior, grounded in the current implementation — design traces CLI/callback/runner/verification/Journal coupling and defines external execution and verification, immutable task bindings and fenced recovery; 2026-10-02 10:51 ET.
- [x] Remove the active Claude implementation assignment and update research recommendations to prioritize control decoupling — former handoff renamed to Codex implementation notes, prior ticket marks assignment withdrawn, parsing report links the control design first; 2026-10-02 10:51 ET.
- [x] Verify design references and acceptance criteria; distinguish design validation from runtime tests — 16 local links/anchors resolve; interface/recovery/acceptance/ownership sections checked; git diff --check passes, runtime qualification explicitly unperformed; 2026-10-02 10:51 ET.
- [ ] Commit and push the design and ownership correction; open and verify a review PR.

## Scope

Design and agent instructions. Runtime implementation, migrations and deployment
are subsequent work; this ticket does not claim the coupling has been removed.
Keep existing tested parser behavior as external workload implementation while
removing its dependency from the proposed Bookkeeping control process.
