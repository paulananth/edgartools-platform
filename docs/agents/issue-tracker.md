# Issue tracker: Local Markdown

Issues and specs for this repository live as Markdown files under `.scratch/`.

## Conventions

- One feature or effort per directory: `.scratch/<feature-slug>/`.
- A specification, when present, is `.scratch/<feature-slug>/spec.md`.
- Implementation issues are one file per ticket at `.scratch/<feature-slug>/issues/<NN>-<slug>.md`, numbered from `01`.
- Triage state is recorded as a `Status:` line near the top of each issue file.
- Comments and conversation history append under a `## Comments` heading.

## Publishing and fetching

- To publish to the issue tracker, create the appropriate Markdown file under `.scratch/<feature-slug>/`.
- To fetch a ticket, read the referenced issue file directly.

## Wayfinding operations

- **Map:** `.scratch/<effort>/map.md` contains the Destination, Notes, Decisions so far, Not yet specified, and Out of scope sections.
- **Child ticket:** `.scratch/<effort>/issues/NN-<slug>.md` contains the question. A `Type:` line records `research`, `prototype`, `grilling`, or `task`; a `Status:` line records `open`, `claimed`, or `resolved`.
- **Blocking:** A `Blocked by: NN, NN` line lists prerequisite tickets. A ticket is unblocked when every listed ticket is resolved.
- **Frontier:** Scan the effort's issues for the first open, unblocked, unclaimed ticket by number.
- **Claim:** Set `Status: claimed` before beginning work.
- **Resolve:** Append the answer under `## Answer`, set `Status: resolved`, and append a linked one-line gist to the map's Decisions-so-far section.
