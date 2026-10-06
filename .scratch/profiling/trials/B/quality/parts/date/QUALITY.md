# Data quality plan: date

Version **contoso-date-quality-trial**. Each check's `on_fail`, and each fix, is a proposal: the operator decides each one.

| Check or fix | Engine | Reads | on_fail | Rows found |
|---|---|---|---|---|
| code_list_year | in_set@1 | fields.year | flag | 0 |
| code_list_year_quarter_number | in_set@1 | fields.year_quarter_number | flag | 0 |
| code_list_quarter | in_set@1 | fields.quarter | flag | 0 |
| code_list_year_month_short | in_set@1 | fields.year_month_short | flag | 0 |
| code_list_year_month_number | in_set@1 | fields.year_month_number | flag | 0 |
| code_list_month_short | in_set@1 | fields.month_short | flag | 0 |
| code_list_month_number | in_set@1 | fields.month_number | flag | 0 |
| code_list_dayof_week_short | in_set@1 | fields.dayof_week_short | flag | 0 |
| code_list_dayof_week_number | in_set@1 | fields.dayof_week_number | flag | 0 |
| code_list_working_day | in_set@1 | fields.working_day | flag | 0 |

Examples per item are in the findings (`quality`), masked for a personal column.
