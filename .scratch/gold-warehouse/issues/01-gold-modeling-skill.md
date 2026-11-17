# Gold warehouse section in the data-modeling skill

Status: claimed
Type: task

## Parts

- [x] Research warehouse techniques and classify the registered silver grains (transaction, periodic snapshot, accumulating snapshot, bridge). Spec `load_mode` checked: line items, measures and the relationship table are `snapshot`; holdings, custody and registration are `append`. 2026-11-16 19:34 ET
- [x] Write `skills/data-modeling/GOLD.md` and the pointers in `SKILL.md`, `REQUIREMENTS.md` and `skills/README.md`. 2026-11-16 19:34 ET
- [x] Genericity, skill-length and guide-path tests. `uv run --no-project --with pytest -- pytest -q -p no:cacheprovider tests/unit/test_profiling_genericity.py tests/unit/test_skills_cite_no_ticket.py tests/unit/test_guides_name_existing_paths.py`: 127 passed. `SKILL.md` 453 lines. 2026-11-16 19:34 ET
- [ ] Publish the skill PR.
- [x] Learning → skill: data-modeling `GOLD.md` — Gold is a conformed dimensional bus over the approved mirror; MDM, RDM and silver stay the integrated store. An append-only reported position stays a transaction fact until a requirement names which correction wins. 2026-11-16 19:34 ET

## Scope

The operator asked for the Gold warehouse section in the data-modeling skill, researched across warehouse techniques and analysed on this platform's registered silver grains. The skill proposes the model. It does not write dbt, approve an exposure list, or create a mirror.

## Decision

The integrated store is already MDM, RDM, silver and the relationship bridge. Gold's model of record is a Kimball bus: one fact per silver grain, conformed dimensions on the master id, business time and recorded time as two date roles. A Data Vault, an anchor model or a second normalized core would master the same entities again. A wide table or an activity stream is a mart of one fact after that fact exists. A 13F position and an N-PORT holding share the instrument dimension and stay separate facts. A filing grain that includes the manager must not be joined on the report key alone. Insider lines and reporting owners stay separate facts until a source pairs them.
