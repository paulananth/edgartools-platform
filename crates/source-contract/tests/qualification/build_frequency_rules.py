"""Generate the two reviewed Name Frequency projections; --check never writes."""
import argparse
from copy import deepcopy
from pathlib import Path
import re
from edgar_warehouse.rules import files
from edgar_warehouse.mdm.clean import company_source, cascade
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--check', action='store_true')
args = parser.parse_args()
root=files.ROOT/'sources/gleif'

def emit(name, content):
    path = root / name
    if args.check:
        if path.read_text() != content:
            raise SystemExit(f'{path}: generated Rules differ; regenerate and review')
    else:
        path.write_text(content)
constant=lambda v:({'equal':{'left':{'const':{'value':0}},'right':{'const':{'value':0 if v else 1}}}} if type(v) is bool else {'const':{'value':v}})
value_at=lambda p:{'value':{'path':p}}
test_at=lambda p,k='truthy':{'test':{'path':p,'kind':k}}
equals=lambda a,b:{'equal':{'left':a,'right':b}}
choose=lambda c,a,b:{'choose':{'condition':c,'then':a,'else':b}}
object_of=lambda f,**kw:{'object':{'fields':f,**kw}}
project=lambda v,t:{'project':{'value':v,'then':t}}
transform=lambda v,ops:{'transform':{'value':v,'transforms':ops}}
text_or_empty=lambda p: choose(test_at(p),value_at(p),constant(''))
allof=lambda cs: __import__('functools').reduce(lambda acc,c:choose(c,acc,constant(False)),reversed(cs),constant(True))
identity=files.load(root/'census-identity.yaml')['read']['tables']['mapped']['columns']
extract=lambda name:identity[name]['object']['fields']['value']
mapped=files.load(root/'level1-fields.yaml')['read']['tables']['mapped']['columns']
quality=files.load(root/'quality.yaml')['quality']['gleif.level1.v1']
spec=cascade.spec(company_source.POLICY)
assert len(spec['passes'])==7
words={'STREET':'ST','AVENUE':'AVE','ROAD':'RD','DRIVE':'DR','BOULEVARD':'BLVD','LANE':'LN','PLACE':'PL','COURT':'CT','PARKWAY':'PKWY','HIGHWAY':'HWY','SUITE':'STE','FLOOR':'FL','ROOM':'RM','NORTH':'N','SOUTH':'S','EAST':'E','WEST':'W'}
ops=[{'case':'upper'},{'unicode':'nfkd'},{'strip_combining':True}, {'regex_replace':{'pattern':r'[^\p{L}\p{N}_#/& -]+|_','with':' '}}]
ops += [{'tokens':words}]
ops += [{'regex_replace':{'pattern':r'(?:^|\s)(?:(?:(?:STE|FL|UNIT|RM|APT)\b|#)\s*[A-Z0-9-]+|\d+(?:ST|ND|RD|TH)\s+FL)\b','with':' '}}, {'regex_replace':{'pattern':r'[\s\x1c-\x1f]+','with':' '}},{'trim':True}]
# Python standardizes each newline separately, dropping empty resulting lines.
line=lambda p:transform(value_at(p),[{'lines':ops}])
blank=lambda expression:choose(equals(expression,constant('')),constant(None),expression)
def standard(p):
    fields={k:blank(line(p+'.'+k)) for k in ('street','street2','city')}
    postcode=value_at(p+'.postcode')
    iszip=equals(transform(postcode,[{'regex_replace':{'pattern':r'^\d{5}-?\d{4}$','with':''}}]),constant(''))
    fields['postcode']=choose(iszip,transform(postcode,[{'slice':{'start':0,'end':5}}]),postcode)
    fields.update(region=value_at(p+'.region'),country=value_at(p+'.country'))
    return choose(test_at(p,'object'),object_of(fields,omit_nulls=True),constant(None))
raw=object_of({'fields':mapped['fields'],'matching':mapped['matching'], 'lei':extract('lei'), 'legal':extract('key')})
standardized=object_of({'address':standard('fields.address'),'headquarters_address':standard('matching.headquarters_address')})
stage=project(raw,object_of({'std':standardized},base=value_at('.')))
checks={x['id']:x for x in quality['checks']}
markers=checks['address_not_registered_agent']['args']['markers']
placeholder=checks['street_not_placeholder']['args']['values']
def withheld(p):
    joined=project({'sequence':[text_or_empty(p+'.street'), text_or_empty(p+'.street2')]},{'join':{'path':'.','item_path':'.','item_type':'text','separator':' ','max_items':2}})
    upper=transform(joined,[{'case':'upper'},{'regex_replace':{'pattern':r'[\s\x1c-\x1f]+','with':' '}}])
    matched=equals(transform(upper,[{'regex_replace':{'pattern':r'(?s)^.*(?:'+'|'.join(re.escape(m) for m in markers)+r').*$','with':''}}]),constant(''))
    # Empty addresses are not agent matches.
    agent=choose(equals(upper,constant('')),constant(False),matched)
    clean=transform(text_or_empty(p+'.street'),[{'case':'upper'},{'regex_replace':{'pattern':r'[^\p{L}\p{N}]','with':''}}])
    bad=equals(transform(clean,[{'regex_replace':{'pattern':r'^(?:'+'|'.join(placeholder)+r'|0+)$','with':''}}]),constant(''))
    bad=choose(equals(clean,constant('')),constant(False),bad)
    return choose(agent,constant(True),bad)
stage=project(stage,object_of({'legal_withheld':withheld('std.address'),'headquarters_withheld':withheld('std.headquarters_address')},base=value_at('.')))
fit=choose(allof([test_at('std.headquarters_address.street'), choose(test_at('headquarters_withheld'),constant(False),constant(True))]), value_at('std.headquarters_address'),
    choose(allof([test_at('std.address.street'),choose(test_at('legal_withheld'),constant(False),constant(True))]),value_at('std.address'),
      object_of({'country':{'coalesce':{'values':[value_at('std.headquarters_address.country'),value_at('std.address.country')],'skip':'falsey'}}})))
eligible=allof([{'lookup':{'reference':'entity_statuses','column':'allowed','key':value_at('fields.gleif_entity_status'),'on_missing':'null'}},
   choose({'lookup':{'reference':'refused_registration_statuses','column':'refused','key':value_at('fields.gleif_registration_status'),'on_missing':'null'}},constant(False),constant(True))])
observation=choose(allof([equals(extract('category'),constant('GENERAL')),choose(equals(extract('lei'),constant(None)),constant(False),constant(True))]),
    {'recover':{'codes':['value_type','join_shape'],'value':project(stage,choose(test_at('fields.name'),object_of({'lei':value_at('lei'),'legal':value_at('legal'), 'place':fit,'jurisdiction':value_at('fields.jurisdiction'),
        'eligible':eligible,'last_update':text_or_empty('fields.gleif_last_update'),
        'legal_withheld':value_at('legal_withheld'),'headquarters_withheld':value_at('headquarters_withheld')}),constant(None))), 'fallback':constant(None)}},constant(None))
references={'entity_statuses':{s:{'allowed':True} for s in spec['entity_statuses']},'refused_registration_statuses':{s:{'refused':True} for s in spec['refused_registration_statuses']}}
config={'source':'gleif.level1','execution':{'profile':'source.read','workers':1,'max_artifacts':1},'read':{'format':'json','limits':{'max_bytes':1048576,'max_records':100000},'references':references,'tables':{'mapped':{'each':'.','columns':{'observation':observation}}}}}
emit('census-cascade-record.yaml', '# GENERAL observations through approved mapped fields and quality; no activation.\n'+files.dumps(config))
stream=files.load(root/'census-names-stream.yaml')
stream['read']['references']=references
stream['read']['context']['source_index']={'type':'integer'}
stream['read']['stream']['ordinal_context']='source_index'
stream['read']['stream']['max_output_rows']=10000000
for table in stream['read']['tables'].values():
    table['columns']['source_index']={'context':{'name':'source_index'}}
    table['columns']['cascade']=project({'value':{'path':'.','from':'document'}},observation)
stream['read']['tables']['d_addresses']={'each':{'project':{'value':observation,'on_null':'empty'}},'select':test_at('place.street'),'columns':{
    'street':transform(text_or_empty('place.street'),[{'regex_replace':{'pattern':r'\n[\s\S]*$','with':''}}]),
    'postcode':transform(text_or_empty('place.postcode'),[{'slice':{'start':0,'end':5}}]),'country':text_or_empty('place.country')}}
emit('census-complete-stream.yaml', '# Complete original-source census projection; input-bound wanted/count required.\n# Global addresses include every supported GENERAL occurrence, before candidate eligibility.\n'+files.dumps(stream))
print({'passes':len(spec['passes']),'cascade_bytes':(root/'census-cascade-record.yaml').stat().st_size,'stream_bytes':(root/'census-complete-stream.yaml').stat().st_size})
