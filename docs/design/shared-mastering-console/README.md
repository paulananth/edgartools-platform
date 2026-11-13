# Shared mastering console handoff

- [Implementation design](DESIGN.md): current boundaries, business invariants, entity policies, UI/API contracts, safety, delivery slices and acceptance cases.
- [Interactive UI prototype](prototype.html): invented design data only; local edits/export do not change rules or MDM. Full theme styling uses Tailwind/DaisyUI CDN assets.
- [Proposed architecture](architecture.html) and [editable Archify source](architecture.json): the target components and their responsibilities, not deployed infrastructure.
- [Verification and review](VERIFICATION.md): checks performed and production work that remains.

![Interactive mastering console design preview](prototype-preview.png)

Download the HTML files and open them locally; GitHub does not execute HTML. The architecture viewer is standalone. The prototype's JSON export is a design draft, not an executable policy or a proof result.

Production frontend/backend implementation is specified by DESIGN.md and remains future work. No rule changes, registration, source loads or live stewardship were performed to create this handoff.
