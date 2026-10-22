import re,os,glob,csv,json
csv.field_size_limit(10**9)
ti=re.compile(r'<(?:\w+:)?titleOfClass>\s*([^<]*?)\s*</',re.I)
T=set()
for d in sorted(glob.glob(os.path.expanduser('~/edgar-local-tmp/t13f/unit*'))):
    for p in os.listdir(d):
        q=os.path.join(d,p)
        if p.endswith('.json') or os.path.isdir(q): continue
        T.update(m for m in ti.findall(open(q,errors='ignore').read()) if m)
n13=len(T)
with open(os.environ['NPORT_HOLDINGS'],newline='',errors='ignore') as fh:
    r=csv.reader(fh,delimiter='\t',quoting=csv.QUOTE_NONE); h=next(r); it,ia=h.index('ISSUER_TITLE'),h.index('ASSET_CAT')
    for row in r:
        if len(row)>ia and row[ia]=='EC' and row[it].strip(): T.add(row[it])
json.dump(sorted(T),open(os.environ['TITLES_OUT'],'w'))
print(n13,len(T))
