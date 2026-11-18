# Edgar Intelligence runbook

The operating procedures of the Edgar Intelligence data platform, kept outside every skill so their steps and
dependencies change on their own. A skill says when to use one; the runbook holds the steps.

| Runbook | Use it to |
|---|---|
| [Initialize](init.md) | create a hosted store from nothing, then load every captured source once, in dependency order |
| [Daily run](daily-run.md) | operate a loaded store: a delivery arrives, files or rules change, size a load, watch and recover a run, test a source |
| [CI/CD](ci-cd.md) | promote tested configuration to an environment: approval, release evidence and activation |

Keep a source's runbook current across runs; write references to engine evidence rather than copying operational state
into a second ledger. Store private inventories and captured values outside Git.
