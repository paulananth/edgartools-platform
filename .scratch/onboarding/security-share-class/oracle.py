import re,os,glob,csv,sys,collections,json
csv.field_size_limit(10**9)
def letter(t):
    s=t.strip().upper(); s=re.sub('[^A-Z]+',' ',s); s=' '+s+' '
    s=re.sub('^.* (CL|CLASS|CLS) ','#',s); s=re.sub('^[^#].*$','',s); s=re.sub(' .*$','',s)
    s=re.sub('^#[A-Z][A-Z]+$','',s); return s.replace('#','')
for t,w in [('CAP STK CL A','A'),('Class A Common Stock','A'),('COM',''),('CAP STK CL',''),('CLASS AB COM',''),('CL A-1','A'),('SHS CL B','B'),('CLASS COMMON','')]:
    assert letter(t)==w,(t,letter(t))
# 13F
f13=collections.defaultdict(set)
cu=re.compile(r'<(?:\w+:)?cusip>\s*([^<]*?)\s*</',re.I); ti=re.compile(r'<(?:\w+:)?titleOfClass>\s*([^<]*?)\s*</',re.I)
it=re.compile(r'<(?:\w+:)?infoTable>(.*?)</(?:\w+:)?infoTable>',re.S|re.I)
n13=0
for d in sorted(glob.glob(os.path.expanduser('~/edgar-local-tmp/t13f/unit*'))):
    for p in os.listdir(d):
        if p.endswith('.json') or os.path.isdir(os.path.join(d,p)): continue
        x=open(os.path.join(d,p),errors='ignore').read()
        for b in it.findall(x):
            c=cu.search(b); t=ti.search(b)
            if not c or not t or not t.group(1): continue
            n13+=1; f13[c.group(1).upper()].add(letter(t.group(1)))
# N-PORT
fe=collections.defaultdict(set); fo=collections.defaultdict(set)
with open(os.environ['NPORT_HOLDINGS'],newline='',errors='ignore') as fh:
    r=csv.reader(fh,delimiter='\t',quoting=csv.QUOTE_NONE); hdr=next(r)
    ic,it_,ia=hdr.index('ISSUER_CUSIP'),hdr.index('ISSUER_TITLE'),hdr.index('ASSET_CAT')
    for row in r:
        if len(row)<=ia: continue
        c=row[ic].strip().upper(); t=row[it_]
        if len(c)!=9 or not t.strip(): continue
        (fe if row[ia]=='EC' else fo)[c].add(letter(t))
def summ(m):
    lettered={c:{x for x in s if x} for c,s in m.items()}; lettered={c:s for c,s in lettered.items() if s}
    return dict(cusips=len(m),lettered=len(lettered),conflict=sum(len(s)>1 for s in lettered.values())), {c:next(iter(s)) for c,s in lettered.items() if len(s)==1}
s13,l13=summ(f13); se,le=summ(fe); so,lo=summ(fo)
both=set(l13)&set(le)
out=dict(thirteenf_rows=n13,thirteenf=s13,nport_equity=se,nport_other=so,
  cusips_lettered_in_both=len(both),cross_source_disagree=sum(l13[c]!=le[c] for c in both),
  nport_other_also_equity=len(set(lo)&set(fe)))
print(json.dumps(out,indent=1)); json.dump(out,open('oracle-counts.json','w'),indent=1)
