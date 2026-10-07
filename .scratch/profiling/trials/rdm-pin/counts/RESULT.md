# Full mastering counts run: the RDM pin against the YAML (profiling 02)

Run 2026-10-07, 18:14 to 18:30 ET, on this machine only (no provider request):
`.scratch/profiling/trials/rdm-pin/counts_run.py`, once per variant, each on
its own disposable PostgreSQL 16.

**Input:** company mastering ticket 27's cohort: seven SEC bundles (6,414
Companies, 586 controls) and the 3,755 GLEIF Level 1 records the Name Census
names for them (Golden Copy 2026-09-11). Today's Company policy `54dca664…`
(each bundle's manifest repointed to it). Everything applied twice.

**The only difference:** the SEC place-code map every place-code consumer
reads (`names._EDGAR_ISO`): built from the pinned RDM version (`pin.json`), or
from `rules/reference/sec-place-codes.yaml` as before PR #848 (`yaml.json`).
Both maps: 308 codes, sha256 `b69397ed…`.

| Count | pin | yaml |
|---|---|---|
| Companies | 6,414 | 6,414 |
| Bound by `company-cik` | 6,414 | 6,414 |
| Bound by `sec-gleif-name-jurisdiction` | 2,861 | 2,861 |
| Bound by `sec-gleif-name-postal` | 191 | 191 |
| GLEIF records bound / read as Company | 3,052 / 3,716 | 3,052 / 3,716 |
| Open reviews: binding required / classification deferred | 664 / 312 | 664 / 312 |
| Which record is bound to which master (digest) | `9216cc18…` | `9216cc18…` |
| Second pass changed nothing | yes | yes |
| Seconds | 483 | 464 |

The two reports differ only in the variant's name and the time taken. The
counts also equal ticket 27's Proving Run (the same 6,414 / 2,861 / 191 / 664 /
312), under the policy of that day.

**Conclusion:** with the pin, mastering gives the same counts as with the
YAML. Removing the YAML now waits only for `in_reference@1` to read the pin
(the Codex handoff in ticket 02).
