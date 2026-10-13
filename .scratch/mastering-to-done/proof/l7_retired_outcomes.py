"""Issue 20 L7: what the retired hand-written mapping gives for each test case, run on main.

Writes tests/engine/retired_mapper_outcomes.json. Ran 2026-10-13 06:43 ET on main's
code (a worktree of origin/main first on the path), reading the case builders
from this branch's tests:
    PYTHONPATH=<main worktree> python -I l7_retired_outcomes.py <this worktree>
"""
import copy, importlib.util, json, sys
from datetime import datetime, timezone
from pathlib import Path
import edgar_warehouse
from edgar_warehouse.control_contract import digest
from edgar_warehouse.mdm.clean import adapters
from edgar_warehouse.rules import files
assert "claude-p07r" in edgar_warehouse.__file__, edgar_warehouse.__file__  # main's code
L7 = Path(sys.argv[1])
def load(name):
    spec = importlib.util.spec_from_file_location(name, L7 / "tests/engine" / f"{name}.py")
    m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m); return m
sec, gl = load("test_sec_configured_fields"), load("test_gleif_configured_fields")
def retained(contract):
    body = copy.deepcopy(contract); body["adapter"].pop("reading"); return body
def sec_contract(source): return retained(next(iter(files.source(source)["mdm"].values()))["contract"])
out = {}
for source in sec.SOURCES:
    for value in [' Exact Spelling ', None, '\x1c \x1f', False, 0, [], {}]:
        record = sec.row(source); record['name' if source.endswith('person') else 'entity_name'] = value
        a = sec_contract(source)["adapter"]
        try: r = ('mapped', digest(adapters._fields(record, a)), digest(adapters._matching_values(record, a)))
        except adapters.UnsupportedRecord as e: r = ('deferred', e.reason)
        out[f'sec/exact/{source}/{value!r}'] = r
for value in [None, {}, 'text', [], False, {'street': '\x1c A \x1f', 'city': ' '}, {'street': False}, {'street': 0}, {'street': []}]:
    record = sec.row(sec.SOURCES[0]); record['business_address'] = value
    try: r = ('mapped', digest(adapters._fields(record, sec_contract(sec.SOURCES[0])["adapter"])))
    except adapters.UnsupportedRecord as e: r = ('deferred', e.reason)
    out[f'sec/address/{value!r}'] = r
for source in sec.SOURCES:
    for case in ['valid', 'bad_identity', 'blank_name', 'bad_name', 'unknown_fields']:
        record = sec.row(source)
        if case == 'bad_identity': record['cik'] = 'not-a-cik'
        elif case == 'blank_name': record['name' if source.endswith('person') else 'entity_name'] = ' '
        elif case == 'bad_name': record['name' if source.endswith('person') else 'entity_name'] = False
        elif case == 'unknown_fields': record['unknown'] = {'integer': 18446744073709551615, 'boolean': False, 'null': None}
        pub = {'publication_key': 'fixture', 'revision': 1, 'artifact_sha256': 'a' * 64, 'member': 'fixture'}
        code = next(iter(files.source(source)['mdm']))
        try: r = ('assertion', digest(adapters.normalize(record, source_code=code, contract=sec_contract(source), publication=pub, policy=files.policy())))
        except adapters.UnsupportedRecord as e: r = ('deferred', e.reason, digest(e.detail), e.probable_kind)
        out[f'sec/normalize/{source}/{case}'] = r
record = sec.row(sec.SOURCES[0]); record['last_synced_at'] = datetime(2026, 1, 1, tzinfo=timezone.utc)
a = sec_contract(sec.SOURCES[0])["adapter"]
out['sec/timestamps'] = digest((adapters._fields(record, a), adapters._matching_values(record, a)))
def gmap(member): return retained(files.source('gleif')['mdm'][f'gleif.{member}.v1']['contract'])["adapter"]
def gexpected(row, member): 
    m = gmap(member); return digest({'fields': adapters._fields(row, m), 'matching': adapters._matching_values(row, m)})
for case in ['complete', 'blank', 'missing', 'empty_address', 'null_lines', 'empty_lines']:
    row = gl.raw()
    if case == 'blank': row['Entity']['LegalName'] = {'$': '\x1c\x1f '}
    elif case == 'missing': row = {'LEI': row['LEI'], 'Entity': {'EntityCategory': {'$': 'GENERAL'}}}
    elif case == 'empty_address': row['Entity']['LegalAddress'] = {'FirstAddressLine': {'$': ' '}, 'AdditionalAddressLine': [{'$': ' '}]}
    elif case == 'null_lines': row['Entity']['LegalAddress']['AdditionalAddressLine'] = None
    elif case == 'empty_lines': row['Entity']['LegalAddress']['AdditionalAddressLine'] = []
    out[f'gleif/level1/{case}'] = gexpected(row, 'level1')
for member in ['relationships', 'reporting_exceptions']:
    out[f'gleif/raw/{member}'] = gexpected({'key': False, 'Relationship': {'RelationshipType': {'$': 'IS_DIRECTLY_CONSOLIDATED_BY'}}}, member)
for value in ['plain text', [{'LegalName': {'$': 'hidden'}}], None, False, 0]:
    row = gl.raw(); row['Entity'] = value; out[f'gleif/parents/{value!r}'] = gexpected(row, 'level1')
for value in ['plain text', [{'$': 'hidden'}]]:
    row = gl.raw(); row['Entity']['LegalName'] = value; out[f'gleif/alias/{value!r}'] = gexpected(row, 'level1')
for case in ['valid', 'invalid_lei', 'non_company', 'bad_name', 'bad_address', 'bad_matching']:
    row = gl.raw()
    if case == 'invalid_lei': row['LEI']['$'] = 'not-an-lei'
    elif case == 'non_company': row['Entity']['EntityCategory']['$'] = 'FUND'
    elif case == 'bad_name': row['Entity']['LegalName']['$'] = False
    elif case == 'bad_address': row['Entity']['LegalAddress']['AdditionalAddressLine'] = ['invalid']
    elif case == 'bad_matching': row['Entity']['HeadquartersAddress']['AdditionalAddressLine'] = ['invalid']
    pub = {'artifact_sha256': 'a' * 64, 'member': 'level1', 'publication_key': 'fixture', 'revision': 1, 'effective_at': None}
    body = retained(files.source('gleif')['mdm']['gleif.level1.v1']['contract'])
    try: r = ('assertion', digest(adapters.normalize(row, source_code='gleif.level1.v1', contract=body, publication=pub)))
    except adapters.UnsupportedRecord as e: r = ('deferred', e.reason, digest(e.detail), e.probable_kind)
    out[f'gleif/normalize/{case}'] = r
(L7 / "tests/engine/retired_mapper_outcomes.json").write_text(json.dumps(json.loads(json.dumps(out)), indent=1, sort_keys=True) + "\n")
print(len(out), "cases")
