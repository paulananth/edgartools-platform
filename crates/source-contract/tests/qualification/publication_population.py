import json,hashlib
from pathlib import Path
from edgar_warehouse.rules import files
from edgar_warehouse.workers import source_read
from edgar_warehouse.bookkeeping.clean.artifacts import Artifacts
root=Path('/private/tmp/codex-census-eof-proof');root.mkdir(exist_ok=True);store=Artifacts()
report=json.loads(Path('.planning/workstreams/company-census-evidence/gleif-runtime/level1-json-runtime-parity.json').read_bytes())
publisher=Path('.planning/workstreams/gleif-member-contracts/lei2-publisher-metadata.json').resolve();ref={'uri':publisher.as_uri(),'sha256':hashlib.sha256(publisher.read_bytes()).hexdigest()}
assert ref['sha256']==report['publisher_metadata']['sha256']
meta=json.loads(publisher.read_bytes());source=report['archive'];url=meta['data']['full_file']['json']['url']
binding=store.put(root.as_uri(),{'version':1,'archive':source,'publisher':ref,'publisher_url':url,'authority':'operator-approved pinned publication manifest binding; distinct from syntax/EOF attestation'})
context=store.put(root.as_uri(),{'version':1,'input':ref,'values':{'source_uri':source['uri'],'source_sha':source['sha256'],'source_url':url}})
contract=files.load(files.ROOT/'sources/gleif/publication-level1-json.yaml');contract['execution']['input_sha256s']=[ref['sha256']]
manifest=store.put(root.as_uri(),{'version':2,'contract':store.put(root.as_uri(),contract),'artifacts':[{'input':ref,'context':context}]})
work={'input':manifest,'output':(root/'publisher-reading.json').as_uri(),'checks':['source.output']}
reading=source_read.execute(work,store);assert source_read.verify({**work,'candidate':reading},store)==({'source.output':True},[])
context2=store.put(root.as_uri(),{'version':2,'input':source,'reading':reading,'table':'metadata','columns':{'publication_count':'publication_count'},'checks':{'source_uri':{'input':'uri'},'source_sha':{'input':'sha256'},'source_url':url,'cdf_version':'LEI_3.1','content_date':'2026-09-11T16:00:00+00:00'},'max_rows':1,'max_bytes':1024**2})
_,values,_=source_read._context({'version':2},{'input':source,'context':context2},store)
assert values=={'publication_count':report['metadata']['record_count']}
proof={'publication_count':values['publication_count'],'publisher':ref,'reading':reading,'context':context2,'authority_binding':binding,'authority_remains_separate':True,'archive_eof_proven_by_metadata':False}
(root/'publication-proof.json').write_text(json.dumps(proof,indent=2)+'\n');print(json.dumps(proof))
