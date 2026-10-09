"""Ticket 07: custody over 13 months of ADV bulk files (local read-only copy).

Run in a folder holding each month's IA_ADV_Base_A_*.raw and IA_Schedule_D_5K3_*.raw
(unzipped from the copy), after conv.py (UTF-8, else windows-1252):
    uv run --with duckdb --with numpy python measure.py
"""
import duckdb, sys
sys.path.insert(0,'.'); from lei import ok
c=duckdb.connect()
c.create_function('lei_ok', ok, ['VARCHAR'], 'BOOLEAN', null_handling='special')
c.sql("create table a as select *, filename f from read_csv('IA_ADV_Base_A_*.csv', all_varchar=true, union_by_name=true, filename=true)")
c.sql("create table k as select * from read_csv('IA_Schedule_D_5K3_*.csv', all_varchar=true, union_by_name=true)")
c.sql('''create table fs as select a.FilingID fid, a."1E1" crd, regexp_replace(f,'.*_(\\d{4}-\\d{2}).*','\\1') m, a.DateSubmitted raw, coalesce(try_strptime(a.DateSubmitted,'%m/%d/%Y %I:%M:%S %p'), try_strptime(a.DateSubmitted,'%m/%d/%Y %H:%M')) ts, a."5K1" k1, a."5K2" k2, a."5K3" k3, a."5K4" k4 from a''')
print(c.sql("select m, min(ts), max(ts), count(*) from fs group by 1 order by 1"))
print(c.sql("select max(cast(split_part(split_part(raw,' ',2),':',1) as int)) maxhour, count(*) filter (where cast(split_part(split_part(raw,' ',2),':',1) as int)>12) over12, count(*) n from fs where raw not like '%M'"))
c.sql('''create table ks as select k."Filing ID" fid, k."5K(3)(f)" fv, k."5K(3)(e)" bd, upper(trim(k."5K(3)(a)")) nm, case when lei_ok(k."5K(3)(f)") then 'lei:'||k."5K(3)(f)" when nullif(k."5K(3)(e)",'') is not null then 'bd:'||k."5K(3)(e)" else 'name:'||upper(trim(k."5K(3)(a)")) end cust from k''')
print(c.sql("select count(*) n, count(*) filter (where nullif(fv,'') is not null) f_filled, count(*) filter (where lei_ok(fv)) lei_valid, count(*) filter (where cust like 'lei:%') by_lei, count(*) filter (where cust like 'bd:%') by_bd, count(*) filter (where cust like 'name:%') by_name, count(distinct cust) custodians from ks"))
print(c.sql("select k1,k2,k3,k4, count(*), count(*) filter (where fid in (select fid from ks)) with_rows from fs group by all order by 5 desc limit 10"))
c.sql('''create table sets as select fs.crd, fs.ts, fs.fid, list_sort(list(distinct ks.cust) filter (where ks.cust is not null)) cs, list_sort(list(distinct ks.nm) filter (where ks.nm is not null)) ns from fs left join ks on ks.fid=fs.fid group by all''')
c.sql('''create table seq as select *, lag(cs) over w prev, lag(ns) over w pn from sets window w as (partition by crd order by ts)''')
print(c.sql('''select count(*) pairs, count(*) filter (where cs<>prev) changed, count(*) filter (where cs<>prev and ns=pn) id_flip_only, count(*) filter (where cs<>prev and ns<>pn) real_change, count(distinct crd) filter (where cs<>prev and ns<>pn) advisers from seq where len(cs)>0 and len(prev)>0'''))
print(c.sql('''select crd, ts, prev, cs from seq where len(cs)>0 and len(prev)>0 and cs<>prev and ns<>pn limit 4'''))
