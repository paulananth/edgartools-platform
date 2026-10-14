"""Measure `sec-ownership-person` on the local ownership copies (offline).

Each filing is read by the approved source extract for its shape; the rule runs on
each reporting owner row. Its label is the proven rule (`sec-person-candidate`,
switched on 2026-10-01 on 720 hand-checked labels) run on that owner's own SEC
submissions document from the pinned capture (all-76230). Writes counts only, and
the CIKs of the person verdicts the proven rule left undecided (for the operator's
check) to a local file outside the repo.

    uv run --no-sync python .scratch/onboarding/sec.ownership/measure.py <counts.json> <local-undecided.json> [<local-checked.json>]

The optional third file lists the CIKs the operator checked as people (outside the
repo; the 31 the proven rule left undecided, operator 2026-10-14: "All 31 are people
(Recommended)"); they count as labelled people.
"""
import json,os,re,pathlib,collections,sys
from edgar_warehouse.rules import files
from edgar_warehouse.rules.source_engine import SourceEngine, SourceRejected
from edgar_warehouse.mdm.clean.classification import fired, resolve_rule
F=files.ROOT/'sources'/'sec.ownership'
XML=SourceEngine(files.load(F/'ownership-xml.yaml')); SGML=SourceEngine(files.load(F/'ownership-sgml.yaml'))
pol=files.policy(); doc=pol['kinds']['person']
new=resolve_rule(pol,{"kind":"person","rule_id":"sec-ownership-person","version":"2026-10-13.1"})
old=resolve_rule(pol,{"kind":"person","rule_id":"sec-person-candidate","version":"2026-09-30.1"})
CAP=pathlib.Path.home()/".local/share/edgartools/clean-mdm/captures/sec.submissions.company/all-76230"
paths={}
for line in open(CAP/"receipts.jsonl"):
    k=json.loads(line).get("key",""); m=re.search(r"CIK(\d{10})\.json$",k)
    if m and "/pagination/" not in k: paths[int(m.group(1))]=CAP/"bronze"/k.removeprefix("warehouse/bronze/")
root=pathlib.Path.home()/'.local/share/edgartools/clean-mdm/proving/p07/inputs/warehouse/bronze'
labels={}
checked=set(json.load(open(sys.argv[3]))) if len(sys.argv)>3 else set()
def label(cik):
    if cik not in labels:
        p=paths.get(cik); labels[cik]=fired(old,json.loads(p.read_text()),doc)[0] if p else 'no document'
        if cik in checked and labels[cik]=='deferred': labels[cik]='person'
    return labels[cik]
tab=collections.Counter(); refused=collections.Counter(); files_=0; rows=0; persons=collections.defaultdict(set)
by_step=collections.defaultdict(lambda: collections.defaultdict(set)); entity_owners=set(); called_person=set()
for d,_,fs in os.walk(root):
    if 'iapd' in d: continue
    for f in fs:
        b=(pathlib.Path(d)/f).read_bytes()
        if b'ownershipDocument' not in b: continue
        files_+=1
        try:
            if b.lstrip().startswith(b'<SEC-DOCUMENT>') or b'<XML>' in b: t=SGML.read(b).tables
            else:
                m=re.search(r'(\d{10}-\d{2}-\d{6})',str(pathlib.Path(d)/f)); t=XML.read(b,context={'accession':m.group(1) if m else f}).tables
        except SourceRejected as e:
            refused[getattr(e,'code',type(e).__name__)]+=1; continue
        for r in t['reporting_owner']:
            rows+=1; v,s=fired(new,r,doc); cik=int(r['rpt_owner_cik'])
            tab[(v,label(cik))]+=1
            if label(cik)=='entity_undetermined': entity_owners.add(cik)
            if v=='person':
                persons[label(cik)].add(cik); by_step[s][label(cik)].add(cik); called_person.add(cik)
print('files',files_,'refused',dict(refused),'owner rows',rows)
for (v,l),n in sorted(tab.items(),key=lambda x:-x[1]): print(f'rule {v:22s} label (proven rule on submissions) {l:22s} rows {n}')
json.dump({'filings':files_,'owner_rows':rows,'refused':dict(refused),
           'rows':{f'{v} | {l}':n for (v,l),n in sorted(tab.items())},
           'person_owners_by_label':{k:len(v) for k,v in persons.items()},
           # Each person step's owners, by label (an owner seen as both director and
           # officer counts under each step that fired for it).
           'person_owners_by_step':{s:{l:len(c) for l,c in d.items()} for s,d in sorted(by_step.items())},
           # Adversarial: every owner the proven rule calls an entity; none may be a person here.
           'adversarial':{'n':len(entity_owners),'violations':len(entity_owners & called_person)}},open(sys.argv[1],'w'),indent=1,sort_keys=True)
json.dump(sorted(persons.get('deferred',())),open(sys.argv[2],'w'))
print({k:len(v) for k,v in persons.items()})
