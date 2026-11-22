# MDM lifecycle and refining-rules ownership

Status: resolved

- [x] Place refining-rules within MDM Engineering and retain compatible routing: the procedure lives in MDM Engineering, with a relative symlink preserving the old skill path, headings and commands. 2026-11-21 19:35 ET
- [x] Incorporate implementation, merging, stewardship, multi-domain and RDM guidance in the README and the linked MDM lifecycle guide. 2026-11-21 19:35 ET
- [x] Update the Archify organization chart with nested MDM/refinement: automated validation, provenance and browser checks passed; canonical SVG exported. 2026-11-21 19:35 ET
- [x] Validate affected documentation: 147 genericity/guide checks, 17 command/install/skill checks and 210 local links passed; no new tests or production code. 2026-11-21 19:35 ET
- [x] Review Standards, Spec and GoF: no content/design findings; Standards' SVG whitespace and receipt-location cleanup completed and checked. 2026-11-21 19:35 ET
- [x] Learning → skill: MDM Engineering owns refinement as a configuration-first subworkflow; its entry point links the sole procedure and MDM lifecycle guidance. 2026-11-21 19:35 ET

## Answer

The refinement procedure moved into `skills/mdm-engineering/REFINING-RULES.md`.
The former `skills/refining-rules/SKILL.md` entry point is a relative symlink,
preserving existing invocations, section links and command validation without
maintaining two procedures. The installed-tree portability test passed. MDM
Engineering remains below the 500-line skill limit.

The root README and `MDM-LIFECYCLE.md` cover governance, modeling, integration,
profiling/quality/matching, stewardship, relationships and publication, plus
the source-to-master merging journey, multi-domain MDM, RDM and people roles.
They retain this platform's capture-first processing, separate MDM/RDM/Silver
responsibilities, configuration-first changes and existing authorization gates.
Operational golden records and analytical linked views are consumption patterns;
generic source-system write-back is not claimed as an implemented feature.

## Standards

Links, command validation, installed skill portability and genericity checks
passed. Generated delivery receipts remain in ignored `.archify` evidence;
the exported SVG has whitespace-only CSS cleanup.

## Spec

The six-role chart now nests MDM Engineering and refining rules beneath the
Data Engineer. README and lifecycle guidance incorporate the supplied MDM
steps and roles without claiming every example domain is configured.

## GoF

No production-code design change. Keep one refinement procedure and preserve
the existing entry point; no new abstraction is justified.
