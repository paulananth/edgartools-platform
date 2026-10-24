# 131: A field kept only when its sources agree

Priority: 131, tier 2. Map: [Rebuild priorities](../map.md). Opened 2026-10-22
from [130: A Security's share class](130-a-security-share-class.md).

**Question:** how does a kind say that a field is kept only when every source
that fills it states the same value, and is otherwise empty and listed for a
steward?

**Why:** the operator's share-class rule (2026-10-22, "Approve the rule
(Recommended)") says filers that disagree give no letter. Each source applies
it to its own filers (ticket 130), but across sources the merge's field rule
only ranks them: the first-ranked source wins (N-PORT before 13F). Measured on
the local copies: 777 CUSIPs carry a letter in both sources, and 1 disagrees.
That Security takes N-PORT's letter, and no steward sees it, because each
source's quality check sees only its own filers.

**What it needs:** a field rule in `rules/merge/kinds/<kind>.yaml` beside
`sources` (for example "agree or none"), and its effect in the Merge Stage's
survivorship. That is new code in the merge, so it is built after Codex's
PR #1121, which edits the same files.

**Status:** closed, no code (2026-10-23 19:56 ET): the operator ruled that source priority decides; no "agree or none" field rule is built.

- [x] The operator's ruling (2026-10-23 19:55 ET): "mastering is all about having good values not blanks, use priority agreeing is not nessary for all fields", then, on the two recommendations, "agreed for now one we have actual examples will sharpen this desission". Across sources the first-ranked source wins (for `share_class`, N-PORT before 13F) and the disagreement stays recorded beside the winner (`conflicts`; `conflict_count` in the `master_field` view, `edgar_warehouse/mdm/clean/schema.py:21-31`), so nothing new is built. Within one source ticket 130's rule stays: filers that disagree give no letter, listed by `share_class_one_letter`. Both are revisited once real disagreeing examples exist
- [ ] ~~The Merge Stage applies it; a test with two sources agreeing, disagreeing and one alone~~ not built: the ruling above keeps source priority
- [ ] ~~`share_class` on the Security uses it~~ not built: the ruling above
- [ ] PR, CI green, merge
- [x] Learning → skill: `skills/security-master/SKILL.md`, Survivorship: a disagreement between sources never blanks a field; find one by `conflict_count` (2026-10-23 19:56 ET)
