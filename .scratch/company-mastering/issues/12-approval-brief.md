# Ticket 12: approval brief — no approval requested yet

**Decision for the operator:** Keep the SEC Company matching rule off. The
September 24 revision did not meet the agreed accuracy bar, and the test
designed to find false Companies found 33. Please do not approve this revision.

The current policy digest is
`5f3a5f571f73612e789f6f4d5a1e32eae7d29486a113cc51c106101fa044fdcf`.
A digest is a fingerprint calculated from the exact policy document. If the
rule or any policy setting changes, the fingerprint changes. Approval of one
digest therefore cannot silently carry over to an edited policy. The earlier
approval for `b26ab87c…` was withdrawn; it does not apply here.

If a future revision earns approval, its Company verdict would be allowed to
act on its own when a new SEC record reaches the Stage. The proposed rule
would call `operating` filers Companies and would also call some `other`
filers Companies when they have an industry code and a Company name word.
That second path is how Shell and ASML could be called Companies; Apple and
Microsoft use the first path. A classification alone does not join SEC and
GLEIF records or create a master record. Those still require the separate
binding and publication decisions.

| Path in this revision | Confirmed Companies / 300 hand-read | 95% lower confidence bound | Agreed minimum |
| --- | ---: | ---: | ---: |
| Step 2: SEC says `operating` | 297 / 300 | 97.52% | 95% — passes |
| Step 4: SEC says `other`, with an industry code and Company word | 258 / 300 | **82.38%** | 95% — **fails** |

Step 4 includes seven identified Funds and 35 serial investment issuers whose
Company status cannot be established from the retained bronze summary. Those
35 are counted against the proof, not asserted to be Funds. Separately, among
483 hand-labeled adversarial records, the rule called **33 Funds or Trusts**
Companies. This is a direct safety failure even if the 35 uncertain cases
are later resolved in the rule's favor. The sample and every label note are
in `../research/12-sample.jsonl` and `../research/12-adversarial.jsonl`.

**Current switch state:** Off. The standard policy has no automatic rule
entry; there is no recorded approval time. Shell and ASML, and Apple and
Microsoft, remain waiting in the Stage on this branch. A future corrected
rule needs another frozen draw for each step, zero adversarial violations,
and the operator's approval of that new policy fingerprint before activation.

**Reversal if a later version is activated:** Remove that version's automatic
rule entry and register a new policy digest. New SEC records then wait in the
Stage. Already published decisions are not erased by changing a policy; they
must be reviewed and corrected through the normal journaled recovery path.
For this revision, no reversal action is needed because it was never switched
on.
