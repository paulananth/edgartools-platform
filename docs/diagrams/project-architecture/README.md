# Project architecture diagrams

The two Archify views describe committed code and configuration at
`8bbeb9981a695a8baea6cddd520cc6cbb78dd5e8`. Their source citations are pinned to
that revision. This is an implementation snapshot, not a live readiness audit.

Each view has an editable JSON candidate, a standalone HTML viewer, and a light
SVG exported through the viewer's canonical export menu. Download the HTML and
open it locally; GitHub renders the SVG previews in the repository README.

| View | Candidate | Viewer | Preview |
| --- | --- | --- | --- |
| Processing and durable data | [JSON](processing.json) | [HTML](processing.html) | [SVG](processing.svg) |
| Rules, work control and verification | [JSON](work-control.json) | [HTML](work-control.html) | [SVG](work-control.svg) |

Both views passed Archify validation, provenance and browser checks. A third view, of Snowflake
serving, was removed with the gold layer.

To regenerate with Archify 3.2, run from the repository root, replacing
`<archify>` with the installed package directory and `<view>` with a table entry:

```bash
node <archify>/bin/archify.mjs finalize architecture \
  docs/diagrams/project-architecture/<view>.json \
  docs/diagrams/project-architecture/<view>.html \
  --repo-root . --quality showcase --json
```

The candidate's output path must match the command's HTML output. Keep the
repository revision pin when reproducing this snapshot; change it and retrace
the citations when updating the architecture. After a delivery reaches browser
checks, give later runs a new `--out-dir` for their evidence. Export SVG · Light
from the regenerated viewer for README previews.
