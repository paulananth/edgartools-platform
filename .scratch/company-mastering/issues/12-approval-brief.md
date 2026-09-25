# Ticket 12: SEC Company rule for operator review

**Current decision state:** The tightened rule has passed its local accuracy
checks. It is still off. No operator approval has been asked for or recorded.

A **policy digest** is a fingerprint of the exact rule document, including
which rules are switched on and their proof. Editing that document changes
the fingerprint, so approval for one digest cannot carry over to an edited
rule. The current inactive policy digest is
`9a9ee48be44454986f02703d966c0b1dce53ac2d5baebd51289316424e047bad`.
It is a review anchor, **not** an approval request for activation. A final
active policy will have a different digest because it must include the true
operator approval details. That exact final document and digest must be
reviewed before registration. The withdrawn approval for an earlier version
does not apply.

If approved and registered, the rule lets its `company` verdict act when a
new SEC filer reaches the Company Stage. In the retained 76,230-filer bronze
population, it would call **7,130** filers Companies: 5,980 because SEC calls
them `operating`, and 1,150 `other` filers because they have an industry code,
a company name word and a nonempty SEC filer category. Apple and Microsoft
take the first path; Shell and ASML take the second. Tim Cook and Satya
Nadella are deferred. Classification lets a record proceed; it does not by
itself join SEC and GLEIF records or publish a Company master. Separate
binding and publication controls still govern those actions.

| Rule path | Confirmed Companies in fresh hand-read sample | One-sided 95% lower bound | Required bound |
| --- | ---: | ---: | ---: |
| Step 2: SEC `operating` | 299 / 300 | 98.52% | 95%, passes |
| Step 4: SEC `other` with industry code, category and company name word | 300 / 300 | 99.11% | 95%, passes |

There was **one error in 600**: "Stonepeak-Plus Infrastructure Fund LP", a
private infrastructure fund that SEC types `operating` (step 2). It is counted
as a Fund, not a Company, on the same standard as the earlier Blackstone
private-equity fund. There were **zero false Company calls in 483
hand-labeled adversarial records**. The fresh draw used seed
`20260924.8`; the previous sample could not measure the change it prompted.
The earlier version called only 258 of 300 step-4 cases correctly and had 33
adversarial violations. Its failure is preserved separately. The samples
measure precision of Company calls, not how many true Companies the rule
misses, and the labels are based on retained bronze summaries and hand
reading rather than an outside registry.

The tighter rule makes some genuine filers wait. The bronze summary has **96**
SEC `other` filers with an industry code, an empty category and a 10-K, 20-F
or 40-F annual filing. Of those, 88 would have matched the old step 4;
ROYAL BANK OF CANADA is an example. They are deferred for review rather than
called Companies on incomplete evidence or treated as failed records. In all,
1,119 old step-4 Company calls now wait because category is empty.

**How to reverse a later activation:** Remove its automatic rule entry in a
new policy document, register the new digest, and new SEC records will wait
in the Stage. Already journaled decisions are not erased by changing policy;
review and correct them through the normal recovery and replay process.
There is nothing to reverse now because the standard rule is still off.
