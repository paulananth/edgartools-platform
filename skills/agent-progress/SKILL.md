---
name: agent-progress
description: Streams evidence-backed progress and inline results in the current agent conversation. Use when asked for live updates, an in-chat progress visual, or a walkthrough of an agent run, regardless of the task domain.
---

# Agent progress

Keep the work in the current conversation. This skill reports progress; it does not authorize work or change the task's approval gates.

1. **Choose the surface.** Use the host's user-visible, non-final progress channel (`out://` in omp). If there is none, put the observed milestones in the final reply. Append-only messages are not a live-updating widget. Do not open a browser or start a server to compensate. Use an in-place card only if the current host has a verified update mechanism.
2. **Acknowledge once.** For work worth tracking, name the task and the next checkpoint in one line. Say “Starting” before dispatch and “Running” only after the tool or job confirms it. For quick work, give the result directly.
3. **Publish changes, not polls.** Update on a verified checkpoint, a blocker, a request for input, or a terminal result. Combine small changes. Use a stable task label or run ID when work overlaps. Name what changed and why it matters. Use a counter only when both completed work and total are measured in the same units. For unknown totals, show the current activity without percent or ETA. Distinguish waiting on the system from waiting for the user; for the latter, state exactly what decision or input is needed.
   For a user decision, carry forward the relevant prior choice or finding, ask one question that unblocks the current step, and say what the answer lets you do. Let the user answer in the same conversation; reminders should be timely and actionable, not repeated with every poll.
4. **Disclose details on demand.** Put the state, evidence, and next action first. Offer named details such as “Show the full rule” or “Show failing checks” only when useful. Keep blockers visible. Share only evidence safe for this conversation, not private reasoning, secrets, or raw sensitive logs.
5. **Close on evidence.** Report `Complete`, `Failed`, `Cancelled`, or `Status unavailable` only as supported by the run. If work continues after the turn, say what is still running. Use a compact table for comparisons; separate what passed from what was not checked. A stop request is not confirmation of cancellation or rollback.

## Examples

- **Measured job:** “Verifying files · 8 of 20 checked.” Post again when the batch finishes or a failure needs attention, not each time a poll returns 8.
- **Research:** “Two primary sources agree on the API contract. The third describes an older version; checking which version the project uses.”
- **Waiting for a decision:** “Report review · The checks passed, but two fields disagree. Which field is authoritative: the source value or the mapped value? That choice determines the comparison rule.”
- **Rule trial:** “Full rule expanded: `is present` → `present@1`.” End with expected versus observed behavior, not just “Try completed.”

When designing feedback or motion for a host-rendered component, read [Microinteraction design](MICROINTERACTIONS.md).
