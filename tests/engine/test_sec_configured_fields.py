"""SEC native mapping must preserve typed values and complete assertions."""
import copy
import json
import pytest
from edgar_warehouse.control_contract import digest
from edgar_warehouse.mdm.clean import adapters
from edgar_warehouse.rules import files,source_engine

SOURCES=('sec.submissions.company','sec.submissions.person')


def contracts(source):
    configured=next(iter(files.source(source)['mdm'].values()))['contract']
    retained=copy.deepcopy(configured);retained['adapter'].pop('reading')
    return configured,retained


def row(source):
    if source.endswith('person'):
        return {'cik':1214156,'name':'COOK TIMOTHY D','entityType':'other','ein':None,'sic':'',
                'fiscalYearEnd':None,'stateOfIncorporation':''}
    return {'cik':320193,'entity_name':'Apple Inc.','entity_type':'operating','sic':'3571',
            'tickers':['AAPL'],'forms':['10-K'],'state_of_incorporation':'CA','fiscal_year_end':'0930',
            'business_address':{'street':' 1 Main Street ','street2':' Suite 2 ','city':' Cupertino ',
                                'region':' CA ','postal_code':'95014-1234','country':'US'},
            'last_synced_at':'2026-01-01T00:00:00+00:00','last_sync_run_id':'fixture',
            'raw_object_id':'a'*64,'name_census':{'version':'fixture','unknown':None,'count':0}}


@pytest.mark.parametrize('source',SOURCES)
def test_inline_native_reading_matches_bundled_recipe(source):
    configured,_=contracts(source)
    recipe=files.load(files.ROOT/'sources'/source/'fields.yaml')
    assert digest(configured['adapter']['reading'])==digest(recipe)


@pytest.mark.parametrize('source',SOURCES)
@pytest.mark.parametrize('value',[' Exact Spelling ',None,'\x1c \x1f',False,0,[],{}])
def test_exact_values_and_invalid_shapes_match_retained_mapping(source,value):
    record=row(source);record['name' if source.endswith('person') else 'entity_name']=value
    configured,retained=contracts(source)
    def mapped(body):
        try:
            return ('mapped',digest(adapters._fields(record,body['adapter'])),
                    digest(adapters._matching_values(record,body['adapter'])))
        except adapters.UnsupportedRecord as error: return ('deferred',error.reason)
    assert mapped(configured)==mapped(retained)


@pytest.mark.parametrize('value',[None,{},'text',[],False,{'street':'\x1c A \x1f','city':' '},
                                  {'street':False},{'street':0},{'street':[]}])
def test_company_address_group_preserves_dictionary_path_semantics(value):
    record=row(SOURCES[0]);record['business_address']=value
    configured,retained=contracts(SOURCES[0])
    def mapped(body):
        try: return ('mapped',digest(adapters._fields(record,body['adapter'])))
        except adapters.UnsupportedRecord as error:return ('deferred',error.reason)
    assert mapped(configured)==mapped(retained)


@pytest.mark.parametrize('source',SOURCES)
@pytest.mark.parametrize('case',['valid','bad_identity','blank_name','bad_name','unknown_fields'])
def test_normalization_preserves_assertion_ids_classification_quality_and_deferrals(source,case):
    record=row(source)
    if case=='bad_identity': record['cik']='not-a-cik'
    elif case=='blank_name':record['name' if source.endswith('person') else 'entity_name']=' '
    elif case=='bad_name':record['name' if source.endswith('person') else 'entity_name']=False
    elif case=='unknown_fields':record['unknown']={'integer':18446744073709551615,'boolean':False,'null':None}
    configured,retained=contracts(source)
    publication={'publication_key':'fixture','revision':1,'artifact_sha256':'a'*64,'member':'fixture'}
    code=next(iter(files.source(source)['mdm']))
    def normalized(body):
        try:
            return ('assertion',digest(adapters.normalize(record,source_code=code,contract=body,
                       publication=publication,policy=files.policy())))
        except adapters.UnsupportedRecord as error:
            return ('deferred',error.reason,digest(error.detail),error.probable_kind)
    assert normalized(configured)==normalized(retained)


def test_company_metadata_timestamps_do_not_enter_the_declared_json_projection():
    from datetime import datetime,timezone
    configured,retained=contracts(SOURCES[0]);record=row(SOURCES[0])
    record['last_synced_at']=datetime(2026,1,1,tzinfo=timezone.utc)
    expected=(adapters._fields(record,retained['adapter']),adapters._matching_values(record,retained['adapter']))
    actual=(adapters._fields(record,configured['adapter']),adapters._matching_values(record,configured['adapter']))
    assert digest(actual)==digest(expected)


@pytest.mark.parametrize('inputs',[None,[],['entity_name','entity_name'],['nested.field'],[False],['x']*129,'name'])
def test_invalid_declared_json_input_fields_fail_closed(inputs):
    configured,_=contracts(SOURCES[0]);configured=copy.deepcopy(configured)
    configured['adapter']['reading']['input_fields']=inputs
    with pytest.raises(source_engine.SourceRejected) as failure:adapters._fields(row(SOURCES[0]),configured['adapter'])
    assert failure.value.code=='contract'


def test_company_json_input_roots_cover_every_declared_value_path():
    configured,_=contracts(SOURCES[0]);reading=configured['adapter']['reading']
    roots=set()
    def visit(node):
        if isinstance(node,dict):
            if 'value' in node:roots.add(node['value']['path'].split('.')[0])
            for value in node.values():visit(value)
        elif isinstance(node,list):
            for value in node:visit(value)
    visit(reading['read']['tables']['mapped']['columns'])
    assert set(reading['input_fields'])==roots


def test_declared_json_input_projection_preserves_missing_versus_explicit_null():
    from edgar_warehouse.workers.source_mapping import project_record
    configured,_=contracts(SOURCES[0]);reading=copy.deepcopy(configured['adapter']['reading'])
    reading['read']['tables']['mapped']['columns']['fields']={'object':{'fields':{
        'missing':{'test':{'path':'entity_name','kind':'missing'}}}}}
    assert project_record({},reading,column='fields')=={'missing':True}
    assert project_record({'entity_name':None},reading,column='fields')=={'missing':False}
