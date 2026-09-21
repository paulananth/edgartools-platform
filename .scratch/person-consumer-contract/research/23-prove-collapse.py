"""Ticket 23: execute the silver collapse logic (old key vs new key) in DuckDB
over the exact rows the dbt unit tests declare, since dbt unit tests need
Snowflake to run. Same SQL shape as the model: qualify row_number() over the
partition, plus the silver_not_retired anti-join."""
import duckdb
con = duckdb.connect()
con.execute("""
create table landing as select * from (values
  (320193,'TEST-SCT-0000001',2023,'Tim Cook',63000000,'2',1),
  (320193,'TEST-SCT-0000001',2022,'Tim Cook',99000000,'2',1),
  (320193,'TEST-SCT-0000001',2021,'Tim Cook',98000000,'2',1),
  (320193,'TEST-SCT-0000002',2023,'Luca Maestri',1,'1',1),
  (320193,'TEST-SCT-0000002',2022,'Luca Maestri',2,'1',1),
  (320193,'TEST-SCT-0000002',2023,'Luca Maestri',27000000,'2',2),
  (320193,'TEST-SCT-0000003',2023,'Kate Adams',5,'2',1),
  (320193,'TEST-SCT-0000003',2022,'Kate Adams',6,'2',1)
) t(cik,accession_number,fiscal_year,exec_name,total_comp,parser_version,parse_sequence);
create table retirement as select * from (values
  ('sec_executive_record','320193|TEST-SCT-0000003|2022|Kate Adams',2)
) r(target_table,business_key,parse_sequence);
""")
def collapse(partition_cols, key_cols):
    part = ", ".join(partition_cols)
    key = "concat_ws('|', " + ", ".join(key_cols) + ")"
    return con.execute(f"""
      select accession_number, fiscal_year, exec_name, total_comp, parser_version
      from landing l
      qualify row_number() over (partition by {part} order by parse_sequence desc) = 1
        and not exists (
          select 1 from (
            select business_key, parse_sequence,
                   row_number() over (partition by business_key order by parse_sequence desc) rn
            from retirement where upper(target_table)=upper('sec_executive_record')
          ) retired
          where retired.rn = 1 and retired.business_key = {key}
            and retired.parse_sequence > l.parse_sequence)
      order by accession_number, fiscal_year desc
    """).fetchall()
old = collapse(["cik","accession_number","exec_name"], ["cik","accession_number","exec_name"])
new = collapse(["cik","accession_number","fiscal_year","exec_name"], ["cik","accession_number","fiscal_year","exec_name"])
print("OLD key (cik, accession, exec_name):")
for r in old: print("   ", r)
print(f"   -> {len(old)} rows; Tim Cook years kept: {sum(1 for r in old if r[2]=='Tim Cook')} of 3")
print("NEW key (cik, accession, fiscal_year, exec_name):")
for r in new: print("   ", r)
print(f"   -> {len(new)} rows; Tim Cook years kept: {sum(1 for r in new if r[2]=='Tim Cook')} of 3")
exp1 = [r for r in new if r[0]=='TEST-SCT-0000001']
exp2 = [r for r in new if r[0]=='TEST-SCT-0000002']
exp3 = [r for r in new if r[0]=='TEST-SCT-0000003']
assert [r[1] for r in exp1] == [2023,2022,2021], "test 1: three years survive"
assert [(r[1],r[3],r[4]) for r in exp2] == [(2023,27000000,'2'),(2022,2,'1')], "test 2: reparse replaces same year only"
assert [(r[1],r[3]) for r in exp3] == [(2023,5)], "test 3: retirement removes one year"
print("all three dbt unit-test expectations reproduce in DuckDB")

# --- Gold: derived columns computed within one filing (Standards review A1).
# Same fixture as models/gold/_executive_records_unit_tests.yml. The OLD
# windows (partition by cik, exec_name order by fiscal_year; rank per cik,
# accession) are shown first to make the tie visible, then the NEW ones.
con.execute("""
create table gold_in as select * from (values
  (320193,'TEST-PROXY-2024',2022,'Tim Cook','CEO',100),
  (320193,'TEST-PROXY-2024',2023,'Tim Cook','CEO',110),
  (320193,'TEST-PROXY-2025',2023,'Tim Cook','CEO',120),
  (320193,'TEST-PROXY-2025',2024,'Tim Cook','CEO',150),
  (320193,'TEST-PROXY-2025',2024,'Luca Maestri','CFO',60),
  (320193,'TEST-PROXY-2025',2022,'Kate Adams','General Counsel',50),
  (320193,'TEST-PROXY-2025',2024,'Kate Adams','General Counsel',55)
) t(cik,accession_number,fiscal_year,exec_name,exec_role,total_comp);
""")
old_gold = con.execute("""
  select accession_number, fiscal_year, exec_name,
         rank() over (partition by cik, accession_number order by coalesce(total_comp,0) desc) as rank_in_filing,
         lag(total_comp) over (partition by cik, exec_name order by fiscal_year) as prior
  from gold_in order by exec_name, accession_number, fiscal_year
""").fetchall()
print("OLD gold windows (rank per filing; lag per (cik, exec_name) by fiscal_year -- tie on FY2023):")
for r in old_gold: print("   ", r)
cook_2024_prior = [r[4] for r in old_gold if r[2]=='Tim Cook' and r[1]==2024][0]
print(f"   -> Tim Cook FY2024 prior-year under OLD windows = {cook_2024_prior} (110 or 120 depending on tie order; unspecified in Snowflake)")
print(f"   -> TEST-PROXY-2025 ranks span {sorted({r[3] for r in old_gold if r[0]=='TEST-PROXY-2025'})} across 5 rows of 3 fiscal years")

new_gold = con.execute("""
  with w as (
    select *,
      rank() over (partition by cik, accession_number, fiscal_year order by coalesce(total_comp,0) desc) as comp_rank_within_filing,
      lag(total_comp) over (partition by cik, accession_number, exec_name order by fiscal_year) as total_comp_prior_year,
      lag(fiscal_year) over (partition by cik, accession_number, exec_name order by fiscal_year) as fiscal_year_prior_row
    from gold_in)
  select accession_number, fiscal_year, exec_name, comp_rank_within_filing,
         case when fiscal_year_prior_row = fiscal_year - 1
               and total_comp_prior_year is not null and total_comp_prior_year <> 0
              then (total_comp - total_comp_prior_year) / total_comp_prior_year end as comp_pct_change_yoy
  from w order by accession_number, fiscal_year, comp_rank_within_filing
""").fetchall()
print("NEW gold windows (within one filing):")
for r in new_gold: print("   ", r)
expect = {
  ('TEST-PROXY-2024',2022,'Tim Cook'):     (1, None),
  ('TEST-PROXY-2024',2023,'Tim Cook'):     (1, 0.1),
  ('TEST-PROXY-2025',2022,'Kate Adams'):   (1, None),
  ('TEST-PROXY-2025',2023,'Tim Cook'):     (1, None),
  ('TEST-PROXY-2025',2024,'Tim Cook'):     (1, 0.25),
  ('TEST-PROXY-2025',2024,'Luca Maestri'): (2, None),
  ('TEST-PROXY-2025',2024,'Kate Adams'):   (3, None),
}
got = {(r[0],r[1],r[2]): (r[3], None if r[4] is None else round(float(r[4]),6)) for r in new_gold}
assert got == expect, f"gold unit-test expectations differ:\n{got}\nvs\n{expect}"
print("the gold dbt unit-test expectations reproduce in DuckDB")
