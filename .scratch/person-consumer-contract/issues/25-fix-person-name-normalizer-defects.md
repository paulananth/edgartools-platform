# Fix three name-normalizer defects before Tier B activates

Type: task
Status: open
Blocked by: none — ships **with** Tier B activation

## Question

Nothing to decide. [Research 21](../research/21-tier-b-8k-extended-labelling.md)
cleared Tier B for 8-K and, in doing so, measured three defects in the name
normalization the key depends on. None is a defect in the key itself
([ticket 20](20-redecide-tier-b-after-calibration.md) Q3 stands unchanged);
all three are in the primitive that parses a name into surname, given name and
middle initial, so they belong to the Mastering Policy's `name_shape`
normalizer rather than to the tier.

1. **Multi-word surnames are mis-parsed.** An EDGAR `LAST FIRST MIDDLE` name
   whose surname carries a particle or is multi-token ("Zegna" brothers) has
   the particle read as the given name. Measured: 0.453% of 8-K and 0.108% of
   Form 3/4/5 records. This is the single false merge the fixed key makes
   against Form 3/4/5's 11 same-issuer homonym CIK pairs — repairing it takes
   that key from 1-of-11 wrong to **0-of-11**.
2. **`V` is treated as a generational suffix.** It discards the middle
   initial of **241** Form 3/4/5 and **7** 8-K records whose middle name is
   simply "V". Drop `V` from the suffix token set; ticket 20's own token list
   (`JR`/`SR`/`II`/`III`/`IV`) is already the correct one and does not include
   it.
3. **Two non-person rows reach the eligible population.** `DATE` and `BANK`
   are missing from the eligibility vocabulary — one of them,
   `Manufacturers Bank`, research 17 had labelled `same`.

Resolved when each is fixed with a regression case and the research 21 census
re-scores unchanged or better.
