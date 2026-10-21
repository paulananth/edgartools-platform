# Pin the independent control wheel in the data-platform installation

- [x] Inspect ownership and update the pinned installation command — operator explicitly assigned the one-line overlap to Codex after the guard identified Grok's older branch; original Grok worktree preserved; 2026-10-21 06:34 ET.
- [x] Verify the command includes every native wheel required by the bundle — all five sources match implementation WHEELS and existing package manifests at the same repository ref; 2026-10-21 06:34 ET.
- [x] Review Standards, Spec and GoF, then open a separate skill PR — no review findings; draft PR #1120, independently committed skill correction; 2026-10-21 06:42 ET.
- [x] Learning → skill: data-platform Setup pins every native dependency to the same repository commit — added the independent control wheel beside the other explicit sources; independent Standards/Spec reviews found no issue, GoF has no applicable code refactor; 2026-10-21 06:34 ET.

Keep the PR draft until the implementation containing the control package is
available at the selected commit. This skill-only branch does not introduce
the native package itself.

The implementation branch's five-wheel Git-ref installation and independent
control architecture cohort passed five cases in 177.72 seconds. This verifies
the added source resolves in the pinned command, with no duplicate shipped
files and every installed module importable. The implementation remains in
progress; this PR remains draft until its dependency is ready.

The platform portability implementation introduces an independent native control
wheel. A Git-based bundle dependency cannot resolve that unpublished wheel
without an explicit source at the same commit. Keep this skill change separate
from engine implementation. Its command applies to a commit containing that
wheel; do not activate or execute any source pipeline.
