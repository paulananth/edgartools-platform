# Support agent setup

The [support](../agents/production-support.toml),
[architecture](../agents/pipeline-architecture-expert.toml) and
[security](../agents/pipeline-security-expert.toml) TOML definitions are real
Codex custom-agent templates, separate from the skill's UI-only `openai.yaml`.
They use `gpt-6-luna` with low reasoning for bounded cost. Escalate a difficult
unresolved question explicitly rather than silently increasing model cost.

In this repository, `.codex/agents/` exposes these canonical definitions for
project-scoped discovery. A skill-wheel installation copies the templates with
the skill, but does not register global agents. To use them elsewhere, copy the
three templates into that trusted project's `.codex/agents/` or the operator's
`~/.codex/agents/`, preserving unrelated definitions. Confirm discovery in a new
session with the installed client; do not claim a current session hot-reloaded.
See [custom agent configuration](https://developers.openai.com/codex/multi-agent/).

The diagnostic roles read evidence and return recommendations. They inherit the
parent's permissions and configured integrations; instructions do not create an
independent read-only sandbox. Use a read-only parent session, restricted
monitoring credentials and authorized bounded/redacted tools. Keep any approved
mutation in a separately authorized owner/executor context. Read-only diagnostic
roles do not execute runbook actions.

For an alert or scheduled review, the existing monitor invokes a bounded parent
investigation with pipeline/run reference, question, redacted evidence references,
lookback, deadline and cost budget. Ask it to use `production-support`, delegating
to `pipeline-architecture-expert` and `pipeline-security-expert` and returning one
consolidated report. Verify the selected host supports that nested delegation;
otherwise the parent must obtain both reviews and pass them into the support
role. Unavailable experts leave the diagnosis incomplete. Existing monitor
integration must be qualified separately before automatic invocation is claimed.
