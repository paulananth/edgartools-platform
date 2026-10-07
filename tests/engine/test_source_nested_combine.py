"""Generic nested composition keeps evidence immutable and ambiguity explicit."""
from copy import deepcopy
import pytest
from edgar_warehouse.bookkeeping.clean.artifacts import Artifacts
from edgar_warehouse.workers import source_combine
from tests.engine.test_source_combine import reading,group,table,join,plan,envelope


def work(root,store,rows,answers,*,drop=('_helper',)):
    refs={'main':reading(store,root,{'company':rows}),'evidence':reading(store,root,{'answers':answers})}
    nested={**join('answers',missing='skip'),'path':['name_census','cascade']}
    config=plan({'answers':group('evidence','answers','cik','answer',mode='one')},
                {'company':{**table('main','company',{'cascade':nested}),'drop':list(drop)}})
    return envelope(store,root,config,refs),config,refs


def test_nested_join_handles_null_parent_missing_answer_and_preserves_shared_evidence(tmp_path):
    store=Artifacts()
    original=[{'cik':1,'name_census':{'key':'A'},'_helper':'A'},
              {'cik':1,'name_census':{'key':'B'},'_helper':'B'},
              {'cik':2,'name_census':None,'_helper':'C'},
              {'cik':3,'name_census':None,'_helper':'D'}]
    task,_,refs=work(tmp_path,store,original,[{'cik':1,'answer':{'lei':'L1'}},{'cik':2,'answer':{'lei':'L2'}}])
    result=source_combine.execute(task,store)
    assert source_combine.verify({**task,'candidate':result},store)==({'source.combined':True},[])
    rows=store.json(result)['artifacts'][0]['tables']['company']
    assert rows==[{'cik':1,'name_census':{'key':'A','cascade':{'lei':'L1'}}},
                  {'cik':1,'name_census':{'key':'B','cascade':{'lei':'L1'}}},
                  {'cik':2,'name_census':{'cascade':{'lei':'L2'}}},{'cik':3,'name_census':None}]
    assert store.json(refs['main'])['artifacts'][0]['tables']['company']==original
    assert store.json(store.json(result)['artifacts'][0]['input'])['readings']==refs


@pytest.mark.parametrize('fault',['duplicate','scalar_parent','leaf_collision','missing_drop'])
def test_ambiguous_or_malformed_composition_refuses_without_publishing(tmp_path,fault):
    store=Artifacts()
    rows=[{'cik':1,'name_census':{'key':'A'},'_helper':'A'}]
    answers=[{'cik':1,'answer':{'lei':'L1'}}]
    if fault=='duplicate': answers.append(deepcopy(answers[0]))
    elif fault=='scalar_parent': rows[0]['name_census']=False
    elif fault=='leaf_collision': rows[0]['name_census']['cascade']={'lei':'EXISTING'}
    else: del rows[0]['_helper']
    task,_,_=work(tmp_path,store,rows,answers)
    with pytest.raises(ValueError): source_combine.execute(task,store)
    assert not (tmp_path/'output').exists()


@pytest.mark.parametrize('fault',[[],['a']*2,['a.b'],['a']*9,'a'])
def test_invalid_nested_path_is_refused_at_contract_validation(tmp_path,fault):
    store=Artifacts()
    task,config,refs=work(tmp_path,store,[{'cik':1,'_helper':'A'}],[])
    config['combine']['tables']['company']['joins']['cascade']['path']=fault
    if fault==['a']*2:
        # Repeated names are valid nested paths; exercise malformed drop instead.
        config['combine']['tables']['company']['drop']=['_helper','_helper']
    with pytest.raises(ValueError): source_combine.execute(envelope(store,tmp_path,config,refs),store)
