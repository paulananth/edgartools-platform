# Account hold-back: SEC Company rule for operator review

**Decision state:** The Account hold-back is proved on the pinned local cohort,
but the standard rule is off. No approval for this version has been recorded.
The pending policy fingerprint is
`31fdbef91859cd8f7423a827ae29156c190b013cff14cde184f3585a2c56f63f`.
It identifies the exact *inactive* policy and its rule version
`sec-company-candidate` `2026-09-25.13`. The activated policy will get a
different fingerprint because it must carry the approval and its real time.

If approved, the rule will let a qualifying SEC filer enter the Company Stage.
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

**Approval gate:** The operator must approve the exact frozen proposal above.
The approval name and actual approval time then enter the policy body, the
rule is activated, and its final digest must be checked before registration.
Activation can be reversed for future records by registering a new policy
without the automatic entry. Previously journaled decisions require review
and evidence replay; changing the policy does not erase them.
