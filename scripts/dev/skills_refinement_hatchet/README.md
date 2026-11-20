# Skill refinement via Hatchet

This local worker orchestrates one ticket at a time. Hatchet persists the implementation and test task states; the implementation and independent test agents use separate configured models in `models.json`:

- Implementation: Claude Code `opus`.
- Test/review: Codex `gpt-6.1-sol`.
- Fallback agent for either lane: Codex `gpt-6-luna`, used only when that lane's primary CLI exits nonzero.

Start the local Hatchet Lite service with `hatchet server start --disable-auth --profile skills-refinement --project-name hatchet-skills-refinement`. Start the worker from this directory with `hatchet worker dev --profile skills-refinement`. Before each ticket run, create its own fresh worktree/branch from `origin/main`; pass that worktree as `--repo` so agents never edit the Hatchet controller checkout or another ticket's branch. Trigger a ticket with `uv run python trigger.py .scratch/onboarding-skill-effectiveness/issues/01-data-platform-responsibility.md --repo /absolute/path/to/ticket-worktree`. For a review-driven revision, add `--review-feedback-file <path>`; the implementation agent must verify those observations before changing files.

The worker does not commit, push, open PRs, access data providers, or perform operational loads. The ticket remains subject to the repository's one-ticket/one-branch/one-PR workflow. Hatchet's local server is only for development and testing; never point this workflow at a production Hatchet tenant.
