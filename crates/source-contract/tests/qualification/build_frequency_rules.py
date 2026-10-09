from copy import deepcopy
from pathlib import Path
import re
from edgar_warehouse.rules import files
from edgar_warehouse.mdm.clean import company_source, cascade
root=files.ROOT/'sources/gleif'
C=lambda v:({'equal':{'left':{'const':{'value':0}},'right':{'const':{'value':0 if v else 1}}}} if type(v) is bool else {'const':{'value':v}})
V=lambda p:{'value':{'path':p}}
T=lambda p,k='truthy':{'test':{'path':p,'kind':k}}
E=lambda a,b:{'equal':{'left':a,'right':b}}
Q=lambda c,a,b:{'choose':{'condition':c,'then':a,'else':b}}
O=lambda f,**kw:{'object':{'fields':f,**kw}}
P=lambda v,t:{'project':{'value':v,'then':t}}
X=lambda v,ops:{'transform':{'value':v,'transforms':ops}}
F=lambda p: Q(T(p),V(p),C(''))
allof=lambda cs: __import__('functools').reduce(lambda acc,c:Q(c,acc,C(False)),reversed(cs),C(True))
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
line=lambda p:X(V(p),[{'lines':ops}])
blank=lambda expression:Q(E(expression,C('')),C(None),expression)
def standard(p):
    fields={k:blank(line(p+'.'+k)) for k in ('street','street2','city')}
    postcode=V(p+'.postcode')
    iszip=E(X(postcode,[{'regex_replace':{'pattern':r'^\d{5}-?\d{4}$','with':''}}]),C(''))
    fields['postcode']=Q(iszip,X(postcode,[{'slice':{'start':0,'end':5}}]),postcode)
    fields.update(region=V(p+'.region'),country=V(p+'.country'))
    return Q(T(p,'object'),O(fields,omit_nulls=True),C(None))
raw=O({'fields':mapped['fields'],'matching':mapped['matching'], 'lei':extract('lei'), 'legal':extract('key')})
standardized=O({'address':standard('fields.address'),'headquarters_address':standard('matching.headquarters_address')})
stage=P(raw,O({'std':standardized},base=V('.')))
checks={x['id']:x for x in quality['checks']}
markers=checks['address_not_registered_agent']['args']['markers']
placeholder=checks['street_not_placeholder']['args']['values']
def withheld(p):
    joined=P({'sequence':[F(p+'.street'), F(p+'.street2')]},{'join':{'path':'.','item_path':'.','item_type':'text','separator':' ','max_items':2}})
    upper=X(joined,[{'case':'upper'},{'regex_replace':{'pattern':r'[\s\x1c-\x1f]+','with':' '}}])
    matched=E(X(upper,[{'regex_replace':{'pattern':r'(?s)^.*(?:'+'|'.join(re.escape(m) for m in markers)+r').*$','with':''}}]),C(''))
    # Empty addresses are not agent matches.
    agent=Q(E(upper,C('')),C(False),matched)
    clean=X(F(p+'.street'),[{'case':'upper'},{'regex_replace':{'pattern':r'[^\p{L}\p{N}]','with':''}}])
    bad=E(X(clean,[{'regex_replace':{'pattern':r'^(?:'+'|'.join(placeholder)+r'|0+)$','with':''}}]),C(''))
    bad=Q(E(clean,C('')),C(False),bad)
    return Q(agent,C(True),bad)
stage=P(stage,O({'legal_withheld':withheld('std.address'),'headquarters_withheld':withheld('std.headquarters_address')},base=V('.')))
fit=Q(allof([T('std.headquarters_address.street'), Q(T('headquarters_withheld'),C(False),C(True))]), V('std.headquarters_address'),
    Q(allof([T('std.address.street'),Q(T('legal_withheld'),C(False),C(True))]),V('std.address'),
      O({'country':{'coalesce':{'values':[V('std.headquarters_address.country'),V('std.address.country')],'skip':'falsey'}}})))
eligible=allof([{'lookup':{'reference':'entity_statuses','column':'allowed','key':V('fields.gleif_entity_status'),'on_missing':'null'}},
   Q({'lookup':{'reference':'refused_registration_statuses','column':'refused','key':V('fields.gleif_registration_status'),'on_missing':'null'}},C(False),C(True))])
observation=Q(allof([E(extract('category'),C('GENERAL')),Q(E(extract('lei'),C(None)),C(False),C(True))]),
    {'recover':{'codes':['value_type','join_shape'],'value':P(stage,Q(T('fields.name'),O({'lei':V('lei'),'legal':V('legal'), 'place':fit,'jurisdiction':V('fields.jurisdiction'),
        'eligible':eligible,'last_update':F('fields.gleif_last_update'),
        'legal_withheld':V('legal_withheld'),'headquarters_withheld':V('headquarters_withheld')}),C(None))), 'fallback':C(None)}},C(None))
references={'entity_statuses':{s:{'allowed':True} for s in spec['entity_statuses']},'refused_registration_statuses':{s:{'refused':True} for s in spec['refused_registration_statuses']}}
config={'source':'gleif.level1','execution':{'profile':'source.read','workers':1,'max_artifacts':1},'read':{'format':'json','limits':{'max_bytes':1048576,'max_records':100000},'references':references,'tables':{'mapped':{'each':'.','columns':{'observation':observation}}}}}
(root/'census-cascade-record.yaml').write_text('# GENERAL observations through approved mapped fields and quality; no activation.\n'+files.dumps(config))
stream=files.load(root/'census-names-stream.yaml')
stream['read']['references']=references
stream['read']['context']['source_index']={'type':'integer'}
stream['read']['stream']['ordinal_context']='source_index'
stream['read']['stream']['max_output_rows']=10000000
for table in stream['read']['tables'].values():
    table['columns']['source_index']={'context':{'name':'source_index'}}
    table['columns']['cascade']=P({'value':{'path':'.','from':'document'}},observation)
stream['read']['tables']['d_addresses']={'each':{'project':{'value':observation,'on_null':'empty'}},'select':T('place.street'),'columns':{
    'street':X(F('place.street'),[{'regex_replace':{'pattern':r'\n[\s\S]*$','with':''}}]),
    'postcode':X(F('place.postcode'),[{'slice':{'start':0,'end':5}}]),'country':F('place.country')}}
(root/'census-complete-stream.yaml').write_text('# Complete original-source census projection; input-bound wanted/count required.\n# Global addresses include every supported GENERAL occurrence, before candidate eligibility.\n'+files.dumps(stream))
print({'passes':len(spec['passes']),'cascade_bytes':(root/'census-cascade-record.yaml').stat().st_size,'stream_bytes':(root/'census-complete-stream.yaml').stat().st_size})
