# Data organization and role skills

[Interactive Archify chart](organization.html) · [SVG preview](organization.svg)
· [Editable candidate](organization.json)

This is a reference organization supplied by the operator, with two peer roles
per function: design/discovery and engineering/production. It does not describe
staffing, deployment or a new approval hierarchy. The lifecycle and skills
coverage are explained in the repository README.

Skill availability follows the maintained [role map](../../../skills/README.md#lifecycle-role-map)
at `369b09f3ff4054a5dc02a61b1d1f8556c382939d`; the candidate pins that evidence.
The Data Engineer branch contains MDM Engineering, which contains the refining
rules subworkflow. These two nested entries describe skill ownership, not
additional employee reporting lines.
The chart includes both available guides and explicit gaps. No job-listing
statistics or claims of production AI/ML readiness are implied.

The HTML passed Archify validation, provenance and automated browser checks.
The SVG is a canonical **SVG · Light** export from that viewer. GitHub renders
the SVG; download the HTML and open it locally to explore role sources and notes.

To regenerate from the repository root with Archify 3.2:

```bash
node <archify>/bin/archify.mjs finalize tree \
  docs/diagrams/data-organization/organization.json \
  docs/diagrams/data-organization/organization.html \
  --repo-root . --quality showcase --out-dir .archify/data-org-review --json
```

Replace `<archify>` with the installed skill directory. Use a fresh `--out-dir`
for each browser-check attempt. Export **SVG · Light** after regeneration.
When updating the mapping, inspect the current skill owners and refresh the
candidate's repository revision and source references together.
