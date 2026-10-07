"""Approved content identity is enforced at the worker and verifier boundary."""
from copy import deepcopy
import pytest
from edgar_warehouse.bookkeeping.clean.artifacts import Artifacts
from edgar_warehouse.workers import source_read


def task(root,store,version=1,pins=None):
    refs=[store.put_bytes((root/f'raw{n}.json').as_uri(),f'{{"n":{n}}}'.encode()) for n in (1,2)]
    execution={'profile':'source.read','workers':2,'max_artifacts':2,'input_sha256s':pins if pins is not None else [r['sha256'] for r in refs]}
    config={'execution':execution,'read':{'format':'json','limits':{'max_bytes':1024,'max_records':10},'tables':{'rows':{'each':'.','columns':{'n':{'value':{'path':'n'}}}}}}}
    contract=store.put(root.as_uri(),config)
    entries=refs if version==1 else [{'input':r,'context':store.put(root.as_uri(),{'version':1,'input':r,'values':{}})} for r in refs]
    manifest={'version':version,'contract':contract,'artifacts':entries}
    work={'input':store.put(root.as_uri(),manifest),'output':(root/'reading.json').as_uri(),'checks':['source.output']}
    return work,manifest,refs


@pytest.mark.parametrize('version',[1,2])
def test_ordered_pins_authenticate_reads_and_refuse_substitution_before_output(tmp_path,version):
    store=Artifacts()
    work,manifest,refs=task(tmp_path,store,version)
    receipt=source_read.execute(work,store)
    assert source_read.verify({**work,'candidate':receipt},store)==({'source.output':True},[])
    assert [a['tables']['rows'][0]['n'] for a in store.json(receipt)['artifacts']]==[1,2]
    bad=deepcopy(manifest)
    bad['artifacts'].reverse()
    changed={**work,'input':store.put(tmp_path.as_uri(),bad),'output':(tmp_path/'rejected.json').as_uri()}
    with pytest.raises(ValueError,match='approved artifact hash'):
        source_read.execute(changed,store)
    assert not (tmp_path/'rejected.json').exists()
    with pytest.raises(ValueError,match='approved artifact hash'):
        source_read.verify({**changed,'output':work['output'],'candidate':receipt},store)
    assert store.json(receipt)['artifacts'][0]['input']==refs[0]


@pytest.mark.parametrize('pins',[[],['0'*64],['0'*64,'G'*64],[False,'0'*64],['0'*65,'0'*64],None])
def test_malformed_or_unapproved_pins_refuse_before_output(tmp_path,pins):
    store=Artifacts()
    work,_,_=task(tmp_path,store,pins=['0'*64,'0'*64] if pins is None else pins)
    with pytest.raises(ValueError): source_read.execute(work,store)
    assert not (tmp_path/'reading.json').exists()
