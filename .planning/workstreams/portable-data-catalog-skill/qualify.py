"""Invented native-API qualification, not a production catalog adapter."""
import json,uuid,traceback
from pathlib import Path
from urllib.parse import quote
import argparse
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
parser=argparse.ArgumentParser(description="Qualify and clean up an invented connected metadata model")
parser.add_argument('--credentials-file',type=Path,required=True)
parser.add_argument('--evidence-dir',type=Path,required=True)
args=parser.parse_args()
settings=json.loads(args.credentials_file.read_text())
base=settings['OPENMETADATA_URL'].rstrip('/')
if not base.endswith('/api/v1'):base+='/api/v1'
def call(method,path,body=None):
 request=Request(base+path,method=method,data=None if body is None else json.dumps(body).encode(),headers={'Authorization':'Bearer '+settings['OPENMETADATA_TOKEN'],'Content-Type':'application/json'})
 try:
  with urlopen(request,timeout=30) as response:
   data=response.read();return json.loads(data) if data else None
 except HTTPError as error:
  if method=='GET' and error.code==404:return None
  raise RuntimeError(f'Native API {method} failed: HTTP {error.code}') from None
 except URLError:
  raise RuntimeError('Native catalog API could not be reached') from None
prefix='portable-catalog-proof-'+uuid.uuid4().hex[:10]
owned=[]; owned_edges=[]; result={'passed':False,'proof_passed':False,'created':0,'removed':0,'lineage_edges_created':0,'lineage_edges_removed':0,'cleanup_errors':0}
private=args.evidence_dir; private.mkdir(parents=True,exist_ok=True)
ledger_path=private/'portable-model-owned.json'
if ledger_path.exists() and not json.loads(ledger_path.read_text()).get('cleanup_complete'):
 raise SystemExit('Prior qualification ownership is unresolved; reconcile its private ledger before another run')
def save_owned():
 ledger=private/'portable-model-owned.json'
 temporary=ledger.with_suffix('.tmp')
 temporary.write_text(json.dumps({'namespace':prefix,'cleanup_complete':result.get('cleanup_passed',False),'objects':[{'endpoint':path,'id':identity,'fqn':name} for path,identity,name,body in owned],'lineage_edges':owned_edges}))
 temporary.chmod(0o600);temporary.replace(ledger)
save_owned()
def create(path,name,body):
 assert call('GET',path+'/name/'+quote(name,safe='')) is None
 answer=call('POST',path,body)
 owned.append((path,answer['id'],name,body)); result['created']+=1;save_owned()
 assert answer['fullyQualifiedName']==name
 return answer
def get(path,name,fields=''):
 return call('GET',path+'/name/'+quote(name,safe='')+('?fields='+fields if fields else ''))
try:
 result['server_version']=call('GET','/system/version').get('version')
 description='Invented portable catalog qualification metadata only.'
 domain=create('/domains',prefix,{'name':prefix,'description':description,'domainType':'Source-aligned'})
 glossary=create('/glossaries',prefix,{'name':prefix,'description':description,'domains':[prefix]})
 parent=create('/glossaryTerms',prefix+'.record',{'name':'record','glossary':prefix,'description':description,'domains':[prefix]})
 termname=prefix+'.record.label'
 term=create('/glossaryTerms',termname,{'name':'label','glossary':prefix,'parent':prefix+'.record','description':'An invented record label.','domains':[prefix]})
 classification=create('/classifications',prefix,{'name':prefix,'description':description})
 tag=create('/tags',prefix+'.example',{'name':'example','classification':prefix,'description':description})
 product=create('/dataProducts',prefix,{'name':prefix,'description':description,'domains':[prefix]})
 service=create('/services/databaseServices',prefix,{'name':prefix,'serviceType':'CustomDatabase','description':description})
 db=create('/databases',prefix+'.example',{'name':'example','service':prefix,'description':description})
 schema=prefix+'.example.flow'
 create('/databaseSchemas',schema,{'name':'flow','database':prefix+'.example','description':description})
 tags=[{'tagFQN':termname,'source':'Glossary','labelType':'Manual','state':'Suggested'}, {'tagFQN':prefix+'.example','source':'Classification','labelType':'Manual','state':'Suggested'}]
 tables=[]
 for name in ['input','output']:
  tables.append(create('/tables',schema+'.'+name,{'name':name,'databaseSchema':schema,'description':description,'domains':[prefix],'dataProducts':[prefix],'columns':[{'name':'label','dataType':'STRING','description':'An invented record label.','tags':tags}]}))
 ps=prefix+'-pipelines'
 create('/services/pipelineServices',ps,{'name':ps,'serviceType':'CustomPipeline','description':description})
 pipeline=create('/pipelines',ps+'.process',{'name':'process','service':ps,'description':description,'tasks':[{'name':'map','downstreamTasks':['publish']},{'name':'publish','downstreamTasks':[]}]})
 details={'pipeline':{'id':pipeline['id'],'type':'pipeline'},'description':description,'columnsLineage':[{'fromColumns':[schema+'.input.label'],'toColumn':schema+'.output.label','function':'copy configured label'}]}
 call('PUT','/lineage',{'edge':{'fromEntity':{'id':tables[0]['id'],'type':'table'},'toEntity':{'id':tables[1]['id'],'type':'table'},'lineageDetails':details}})
 owned_edges.append({'source':tables[0]['id'],'target':tables[1]['id']});result['lineage_edges_created']+=1;save_owned()
 result['created_column_label_counts']=[len(v['columns'][0].get('tags') or []) for v in tables]
 table=get('/tables',schema+'.output','domains,dataProducts,tags,columns')
 assert {v['id'] for v in table['domains']}=={domain['id']}
 assert {v['id'] for v in table['dataProducts']}=={product['id']}
 result['returned_column_labels']=[{'source':v['source'],'state':v['state'],'labelType':v['labelType']} for v in table['columns'][0]['tags']]
 assert {(v['tagFQN'],v['source'],v['state']) for v in table['columns'][0]['tags']}=={(termname,'Glossary','Suggested'),(prefix+'.example','Classification','Suggested')}
 t=get('/glossaryTerms',termname,'domains,parent')
 assert t['parent']['id']==parent['id'] and {v['id'] for v in t['domains']}=={domain['id']}
 graph=call('GET','/lineage/table/'+tables[1]['id']+'?upstreamDepth=1&downstreamDepth=0')
 assert len(graph['upstreamEdges'])==1
 edge=graph['upstreamEdges'][0]['lineageDetails']
 assert edge['pipeline']['id']==pipeline['id'] and edge['columnsLineage']==details['columnsLineage']
 actual=get('/pipelines',ps+'.process','tasks')
 assert {v['name']:v.get('downstreamTasks',[]) for v in actual['tasks']}=={'map':['publish'],'publish':[]}
 # A wrong expected transformation must fail the actual readback comparison.
 wrong=json.loads(json.dumps(details['columnsLineage']));wrong[0]['function']='incorrect expectation'
 try:assert edge['columnsLineage']==wrong
 except AssertionError:result['wrong_mapping_rejected']=True
 else:raise AssertionError('Incorrect mapping was accepted')
 before={(path,name):(get(path,name)['id'],get(path,name)['version']) for path,identity,name,body in owned}
 for path,identity,name,body in owned:
  actual=call('PUT',path,body)
  assert (actual['id'],actual['version'])==before[path,name]
 result['repeat_identity_and_version_unchanged']=True
 result.update(proof_passed=True,domain_associations=2,glossary_hierarchy_links=1,column_glossary_links=2,column_classification_links=2,data_product_memberships=2,field_lineage_edges=1,pipeline_associations=1,task_dependencies=1,quality_results_created=0)
except Exception:
 diagnostic=private/'portable-model-failure.txt';diagnostic.write_text(traceback.format_exc());diagnostic.chmod(0o600)
 result['private_diagnostic']=True
finally:
 for edge in reversed(owned_edges):
  try:
   call('DELETE','/lineage/table/'+edge['source']+'/table/'+edge['target'])
   graph=call('GET','/lineage/table/'+edge['target']+'?upstreamDepth=1&downstreamDepth=0')
   assert not any(item['fromEntity']==edge['source'] for item in graph['upstreamEdges'])
   result['lineage_edges_removed']+=1
  except Exception:
   result['cleanup_errors']+=1
 for path,identity,name,body in reversed(owned):
  try:
   found=get(path,name)
   if found:
    assert found['id']==identity
    call('DELETE',path+'/'+identity+'?hardDelete=true&recursive=false')
    assert get(path,name) is None
   result['removed']+=1
  except Exception:
   result['cleanup_errors']+=1
 result['owned_objects_remaining']=result['created']-result['removed']
 result['owned_lineage_edges_remaining']=result['lineage_edges_created']-result['lineage_edges_removed']
 result['cleanup_passed']=not (result['cleanup_errors'] or result['owned_objects_remaining'] or result['owned_lineage_edges_remaining'])
 result['passed']=result['proof_passed'] and result['cleanup_passed']
 save_owned()
 receipt=private/'portable-model-receipt.json';receipt.write_text(json.dumps(result));receipt.chmod(0o600)
 print(json.dumps(result,sort_keys=True))
 if not result['passed'] or result['cleanup_errors']:raise SystemExit(1)
