# Account hold-back: SEC Company rule for operator review

**Decision state:** The operator approved the frozen Account hold-back proposal
on 2026-09-25. The reply was processed at 2026-09-25 13:09:33 ET
(2026-09-25T17:09:33Z). The rule is active on the Codex branch only; it has
not been registered in a shared database or merged. The approved proposal's
inactive-policy fingerprint is
`31fdbef91859cd8f7423a827ae29156c190b013cff14cde184f3585a2c56f63f`.
It identifies rule `sec-company-candidate` `2026-09-25.13` before activation.
The active policy fingerprint, including approval details, is
`35250dad7c22fe9404abda7af8b6be91fb5cfba43859aa531fcc18e2e0111321`.

The rule lets a qualifying SEC filer enter the Company Stage.
It calls SEC `operating` filers Companies only after holding back fund names,
fund-report filers, private Form 10 plus Form D filers without a BDC election,
and several code, ticker, and category combinations. It also calls an SEC
`other` filer a Company when the filer has an industry code, a nonempty filer
category, and a company legal-form word. Apple and Microsoft take the first
path; Shell and ASML take the second. Tim Cook and Satya Nadella wait.

The frozen bronze population has 76,230 SEC filers. This rule calls 6,414
Companies (5,278 at step 8 and 1,136 at step 10). The other 69,816, or
91.58%, wait in the Stage. Classification alone does not join SEC and GLEIF
or publish a master Company; the separate matching and publication gates
remain open.

| Company path | Labeled Company calls | One-sided 95% lower bound | Required bound |
| --- | ---: | ---: | ---: |
| Step 8, eligible `operating` filer | 300 of 300 | 99.11% | 95% |
| Step 10, eligible `other` filer | 300 of 300 | 99.11% | 95% |

Together the sampled calls are 600 of 600 (lower bound 99.55%). A separate
328-record adversarial draw contains zero labeled non-Companies called Company.
The 34 records held back by the fund-name step contain 16 labeled Funds and
18 labeled Companies, including 13 BDCs. Their Probable Kind remains Fund
Structure; it is a sorting estimate and creates no identity.

The borderline readings follow the operator's settled kinds: the TIAA Real
Estate Account and exchange-traded crypto trusts are Funds; BDCs and listed
royalty trusts are Companies. S-11 publicly offered real-estate partnerships
and government-owned corporations such as the Tennessee Valley Authority
were read as Companies. The pinned label file names the 16 Funds explicitly;
the remaining records receive Company labels with a note derived from their
bronze name, industry code, ticker, category, and filing forms. CI re-scores
those frozen labels and checks that the current rule still makes the same
step decisions. The labels are bronze-based readings, not independent registry
adjudications of all 928 sampled and adversarial records.

The rule uses SEC's newest retained ticker catalog, dated 2026-09-02, and
the recent filing lists from each filer's captured submissions page. Its
precision samples do not measure how many true Companies wait. Re-reading a
committed deferred publication after Probable Kind changes still collides;
that limitation was accepted on 2026-09-23 and requires a separate repair.

**Remaining gate:** The operator approved the frozen proposal above. The
approval name and recorded approval time now live in the policy body, and the
rule is active on this branch. The exact active fingerprint must be checked
before registration; PR #712 remains unmerged until the operator says to merge.
Activation can be reversed for future records by registering a new policy
without the automatic entry. Previously journaled decisions require review
and evidence replay; changing the policy does not erase them.
