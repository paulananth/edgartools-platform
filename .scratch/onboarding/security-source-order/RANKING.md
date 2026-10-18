# Source ranking

Values compared upper case; every run of punctuation or space folded to one space; trimmed. Order by one value, then coverage: the first source wins where it fills a field.

Recommended order for every field: openfigi.security.v1, sec.nport.security.v1, sec.thirteenf.information_table.security.v1.

## issuer_name

405,016 keys filled by at least one source. Recommended order: openfigi.security.v1, sec.nport.security.v1, sec.thirteenf.information_table.security.v1.

| Source | Keys | Coverage | One value |
|---|---:|---:|---:|
| openfigi.security.v1 | 353,491 | 87.3% | 99.7% |
| sec.nport.security.v1 | 385,382 | 95.2% | 62.4% |
| sec.thirteenf.information_table.security.v1 | 29,942 | 7.4% | 59.9% |

| Sources | Keys both fill | Agree |
|---|---:|---:|
| openfigi.security.v1 and sec.nport.security.v1 | 353,491 | 10.5% |
| openfigi.security.v1 and sec.thirteenf.information_table.security.v1 | 8,994 | 63.9% |
| sec.nport.security.v1 and sec.thirteenf.information_table.security.v1 | 10,308 | 76.5% |

## security_title

405,016 keys filled by at least one source. Recommended order: openfigi.security.v1, sec.nport.security.v1, sec.thirteenf.information_table.security.v1.

| Source | Keys | Coverage | One value |
|---|---:|---:|---:|
| openfigi.security.v1 | 353,487 | 87.3% | 100.0% |
| sec.nport.security.v1 | 385,382 | 95.2% | 58.1% |
| sec.thirteenf.information_table.security.v1 | 29,942 | 7.4% | 41.3% |

| Sources | Keys both fill | Agree |
|---|---:|---:|
| openfigi.security.v1 and sec.nport.security.v1 | 353,487 | 0.1% |
| openfigi.security.v1 and sec.thirteenf.information_table.security.v1 | 8,994 | 35.4% |
| sec.nport.security.v1 and sec.thirteenf.information_table.security.v1 | 10,308 | 6.1% |

## security_description

405,016 keys filled by at least one source. Recommended order: openfigi.security.v1, sec.nport.security.v1, sec.thirteenf.information_table.security.v1.

| Source | Keys | Coverage | One value |
|---|---:|---:|---:|
| openfigi.security.v1 | 232,151 | 57.3% | 97.1% |
| sec.nport.security.v1 | 385,382 | 95.2% | 58.1% |
| sec.thirteenf.information_table.security.v1 | 29,942 | 7.4% | 41.3% |

| Sources | Keys both fill | Agree |
|---|---:|---:|
| openfigi.security.v1 and sec.nport.security.v1 | 232,151 | 27.3% |
| openfigi.security.v1 and sec.thirteenf.information_table.security.v1 | 8,935 | 0.0% |
| sec.nport.security.v1 and sec.thirteenf.information_table.security.v1 | 10,308 | 6.1% |

## In the kind file

```yaml
defaults:
  sources:
  - openfigi.security.v1
  - sec.nport.security.v1
  - sec.thirteenf.information_table.security.v1
```
