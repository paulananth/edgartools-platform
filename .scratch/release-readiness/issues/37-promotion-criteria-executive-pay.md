# 37 — Product-ready promotion criteria for Executive / management & pay (F10)

Type: grilling
Status: resolved
Blocked by: 27

## Question

What is the complete, product-ready set of acceptance criteria that must all pass before
Executive/management & pay is promoted from Partial to Covered in the coverage matrix?
Concrete platform surface per the matrix footnote: gold `EXECUTIVE_RECORD` (name, role,
salary/bonus/stock/option/total); MDM person + `EMPLOYED_BY`; Subject Bundle `employment`
(+ proxy pay). Matrix note: "Names/pay/roles only — not full bios or org chart."

Write this as a numbered list of criteria (coverage breadth across DEF 14A filers, pay-field
completeness/correctness against proxy source, `EMPLOYED_BY` graph-edge agreement, Bundle
`employment` section accuracy, explicit scope boundary re: bios/org-chart being out of scope),
each with a concrete, checkable acceptance query or procedure, following the exact method and
rigor of `erdp-coverage-promotion` tickets 03–06 — grounded in real schema/code, cross-checked
against ticket 27's ER-skill survey findings for this product, adversarially stress-tested for
what a naive checklist would miss.

## Answer

Grounded in live schema (`EDGARTOOLS_GOLD.EXECUTIVE_RECORDS` — the actual materialized name;
the matrix footnote's singular `EXECUTIVE_RECORD` doesn't exist, same naming pattern found
across several F1-F12 tables this session) and ticket 27's F10 survey findings. This product is
in noticeably better shape than most of its F1-F12 siblings: real data at real scale, one
already-documented Bundle section (`employment`, explicitly noting "pay from gold proxy").

1. **Coverage — healthy, live-verified.** 13,457 executive-compensation rows across **893**
   distinct CIKs (of ~2,462 operating/issuer-type active companies per ticket 40's breakdown,
   ~36%). This is plausible, not alarming — DEF 14A proxies are filed by established registrants
   with public equity/say-on-pay requirements, not the full operating-issuer population (smaller
   registrants, recent IPOs pre-first-proxy, and foreign private issuers filing 20-F instead of a
   proxy are all legitimately absent). Bar: **≥30%** of active operating companies have at least
   one executive record — comfortably cleared today; this is lower than tickets 28/29's 95% bars
   because, unlike ticker/filing coverage, DEF 14A itself is not universal across all issuers by
   design, not just a data-capture question.
   Acceptance: `SELECT COUNT(DISTINCT cik) * 1.0 / COUNT(DISTINCT c.cik) >= 0.30 FROM COMPANY c
   LEFT JOIN EXECUTIVE_RECORDS er ON er.cik = c.cik WHERE c.tracking_status='active' AND
   c.entity_type='operating'`.

2. **A real, live-found data-quality gap: `exec_role` is only 43% populated.** `exec_name` is
   100% populated (13,457/13,457) but `exec_role` only 5,759/13,457. initiating-coverage's stated
   spec explicitly needs named roles (CEO/CFO always required, +2 other named C-suite) — a
   record with a name but no role cannot satisfy that requirement. This is the real gate here,
   not coverage.
   Acceptance: for CIKs meeting criterion 1, `exec_role` must be non-null for at least the
   top-`COMP_RANK_WITHIN_FILING` executive per filing (the presumptive CEO/CFO) — a full 100%
   bar across every row is not required (per-skill need is CEO+CFO+2 others, not every named
   person in the proxy table), but the top-ranked rows failing this check would be.

3. **Pay-field completeness for the covered subset.** `total_comp` is 92% populated
   (12,418/13,457) among rows that exist — reasonable; verify the remaining 8% isn't concentrated
   in a way that silently drops top-paid executives (e.g., check `total_comp IS NULL` isn't
   correlated with `COMP_RANK_WITHIN_FILING = 1`).

4. **`EMPLOYED_BY` graph-edge agreement.** 51,697 active `EMPLOYED_BY` edges exist (live-checked,
   active generation) — cross-check that CIKs with `EXECUTIVE_RECORDS` rows also have
   corresponding `EMPLOYED_BY` edges (per `docs/subject-bundle-read.md`'s own rule: `employment`
   requires `EMPLOYED_BY` with `source_system` `proxy_def14a` **or** `item_5_02`). A pay record
   with no matching graph edge is a sync gap between MDM and the gold pay table.

5. **Explicit scope boundary: bios/org-chart are out of scope, per the matrix's own note.**
   initiating-coverage's fuller spec (300-400-word bio, prior 2-3 roles, education,
   accomplishments) goes beyond what `EXECUTIVE_RECORDS` (a pay/role fact table) can supply —
   ticket 27's survey already flags that the bio-narrative portion is F3-adjacent (filing-text
   research), not this product's job. This checklist does not require bio content; it requires
   the structured name/role/pay fields the platform surface actually carries.

**Explicitly not required for promotion:** full biographical content, prior-company history,
education, org-chart structure (all explicitly out of scope per the matrix note and ticket 27's
survey — no skill besides initiating-coverage asks for anything beyond event-level "management
change" headlines, and even initiating-coverage's deeper bio need is F3-adjacent, not F10's job).

**Known residual risk:** the 43% `exec_role` gap (criterion 2) is the one real, currently-failing
gate — everything else in this checklist is close to passing today. Worth a lightweight
follow-up to understand why role is missing on the majority of rows (a parser gap on certain
proxy formats, most likely) before treating this product as close to Covered.
