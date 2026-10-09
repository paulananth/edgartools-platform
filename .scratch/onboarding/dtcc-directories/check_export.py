"""Adversarial checks for the exploratory export, independent of DTCC content."""
import hashlib
import json
import tempfile
from pathlib import Path

from openpyxl import Workbook

from export_workbooks import export

with tempfile.TemporaryDirectory() as folder:
    root = Path(folder)
    source = root / 'input.xlsx'
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = 'Accounts'
    sheet.append(['source preamble'])
    sheet.append(['account', 'label'])
    sheet.append(['0005', 'MÜLLER / SERIES II '])
    sheet.append([None, None])
    sheet.append([7, 'numeric source value'])
    workbook.save(source)
    manifest = root / 'manifest.json'
    def receipt():
        manifest.write_text(json.dumps([{'local_file': str(source), 'http_status': 200,
                                        'sha256': hashlib.sha256(source.read_bytes()).hexdigest()}]))
    receipt()
    result = export(manifest, {'input.xlsx': {'Accounts': 2}}, root / 'valid')
    rows = [json.loads(line) for line in Path(result[0]['file']).read_text().splitlines()]
    assert rows == [{'account': '0005', 'label': 'MÜLLER / SERIES II '},
                    {'account': None, 'label': None},
                    {'account': 7, 'label': 'numeric source value'}]
    assert result[0]['first_source_row'] == 3 and result[0]['blank_rows_retained'] == 1
    print('PASS leading zeros, Unicode, whitespace, source types, blanks and coordinates')
    source.write_bytes(source.read_bytes() + b'changed')
    try:
        export(manifest, {'input.xlsx': {'Accounts': 2}}, root / 'corrupt')
    except AssertionError:
        print('PASS changed capture refused')
    else:
        raise RuntimeError('changed capture was accepted')
    sheet['A3'] = '=1+1'
    workbook.save(source)
    receipt()
    try:
        export(manifest, {'input.xlsx': {'Accounts': 2}}, root / 'formula')
    except AssertionError:
        print('PASS formula refused instead of trusting a cached value')
    else:
        raise RuntimeError('formula was accepted')
    sheet['A3'] = '0005'
    sheet['B2'] = 'account'
    workbook.save(source)
    receipt()
    try:
        export(manifest, {'input.xlsx': {'Accounts': 2}}, root / 'header')
    except AssertionError:
        print('PASS duplicate header refused instead of overwriting cells')
    else:
        raise RuntimeError('duplicate header was accepted')
