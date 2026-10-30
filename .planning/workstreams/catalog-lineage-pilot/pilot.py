"""Bounded metadata-only prototype. Not a production publisher or scheduler.

uv run --no-project pilot.py --config example.json --publish
Credentials are read privately from the existing catalog worker file.
"""
import argparse
import html
import json
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen


def validate(config):
    datasets = {item['name']: item for item in config['datasets']}
    stages = {item['name']: item for item in config['stages']}
    if len(stages) != len(config['stages']) or len(datasets) != len(config['datasets']):
        raise ValueError('Duplicate configured identity')
    seen = set()
    for step in config['stages']:
        if not set(step['requires']) <= seen:
            raise ValueError('Missing, cyclic or out-of-order dependency')
        for mapping in step['mappings']:
            inputs = {f['name'] for f in datasets[step['input']]['fields']}
            outputs = {f['name'] for f in datasets[step['output']]['fields']}
            if not set(mapping['from']) <= inputs or mapping['to'] not in outputs:
                raise ValueError('Unresolved field mapping')
        seen.add(step['name'])
    for control in config['controls']:
        if any(item['stage'] not in stages for item in control['interactions']):
            raise ValueError('Unresolved control interaction')
        if any(not isinstance(item.get('label'), str) or not item['label'].strip()
               for item in control['interactions']):
            raise ValueError('Control interaction needs a clear action label')


def description(config):
    text = config['description'] + '\n\n## Processing stages\n'
    for step in config['stages']:
        text += f"\n### {step['title']}\n{step['description']}\n"
        for mapping in step['mappings']:
            text += f"\n- {', '.join(mapping['from'])} → {mapping['to']}: {mapping['transformation']}"
        for check in step['checks']:
            text += '\n- Quality rule: ' + json.dumps(check, sort_keys=True)
    for control in config['controls']:
        text += f"\n\n## Control lane: {control['title']}\n{control['description']}\n"
        for item in control['interactions']:
            text += f"\n- {item['stage']}: {item['description']}"
        text += '\n\nReference: ' + control['reference']
    return text


def connection():
    private = Path.home() / '.local/share/edgartools/catalog/worker.json'
    settings = json.loads(private.read_text())
    base = settings['OPENMETADATA_URL'].rstrip('/')
    if not base.endswith('/api/v1'):
        base += '/api/v1'

    def call(method, endpoint, body=None):
        request = Request(base + endpoint, method=method,
                          data=None if body is None else json.dumps(body).encode(),
                          headers={'Authorization': 'Bearer ' + settings['OPENMETADATA_TOKEN'],
                                   'Content-Type': 'application/json-patch+json' if method == 'PATCH' else 'application/json'})
        try:
            with urlopen(request, timeout=30) as response:
                data = response.read()
                return json.loads(data) if data else None
        except HTTPError as error:
            if method == 'GET' and error.code == 404:
                return None
            raise RuntimeError(f'Catalog API {method} failed: HTTP {error.code}') from None
        except URLError:
            raise RuntimeError('Catalog API could not be reached') from None
    return call


def exercise(config, call):
    """Leave exactly one isolated invented example for the operator to review."""
    validate(config)
    namespace = config['namespace']
    if not namespace.startswith('catalog-lineage-review-'):
        raise ValueError('Pilot requires an isolated review namespace')
    marker = 'Invented lineage review metadata. Not operational data.'
    service = namespace + '-pipelines'
    objects = []

    def put(endpoint, body, name):
        before = call('GET', endpoint + '/name/' + quote(name, safe=''))
        if before and marker not in html.unescape(before.get('description') or ''):
            raise ValueError('Refusing to overwrite metadata not owned by this pilot')
        body = dict(body, description=marker + '\n\n' + body.get('description', ''))
        result = call('PUT', endpoint, body)
        if result.get('fullyQualifiedName') != name:
            raise ValueError('Catalog identity differs from the configuration')
        if html.unescape(result.get('description') or '') != body['description']:
            identity = result['id']
            result = call('PATCH', endpoint + '/' + identity,
                          [{'op': 'add', 'path': '/description', 'value': body['description']}])
            if result['id'] != identity or result.get('fullyQualifiedName') != name:
                raise ValueError('Catalog identity changed while updating its description')
        objects.append((endpoint, name, body))
        return result

    put('/services/databaseServices', {'name': namespace, 'serviceType': 'CustomDatabase'}, namespace)
    database = namespace + '.example'
    schema = database + '.flow'
    put('/databases', {'name': 'example', 'service': namespace}, database)
    put('/databaseSchemas', {'name': 'flow', 'database': database}, schema)
    tables = {}
    for dataset in config['datasets']:
        tables[dataset['name']] = put('/tables', {
            'name': dataset['name'], 'displayName': dataset['title'],
            'databaseSchema': schema, 'description': dataset['description'],
            'columns': [dict(f, dataType='STRING') for f in dataset['fields']]}, schema + '.' + dataset['name'])
    put('/services/pipelineServices', {'name': service, 'serviceType': 'CustomPipeline'}, service)
    tasks = [{'name': step['name'], 'displayName': step['title'], 'taskType': step['operation'],
              'description': step['description'],
              'downstreamTasks': [other['name'] for other in config['stages'] if step['name'] in other['requires']]}
             for step in config['stages']]
    pipeline = put('/pipelines', {'name': config['name'], 'displayName': config['title'],
        'service': service, 'description': description(config), 'tasks': tasks}, service + '.' + config['name'])
    expected_edges = []
    for step in config['stages']:
        source, target = tables[step['input']], tables[step['output']]
        columns = [{'fromColumns': [source['fullyQualifiedName'] + '.' + column for column in mapping['from']],
                    'toColumn': target['fullyQualifiedName'] + '.' + mapping['to'],
                    'function': mapping['transformation']} for mapping in step['mappings']]
        details = {'pipeline': {'id': pipeline['id'], 'type': 'pipeline'},
                   'description': step['description'], 'columnsLineage': columns}
        call('PUT', '/lineage', {'edge': {'fromEntity': {'id': source['id'], 'type': 'table'},
             'toEntity': {'id': target['id'], 'type': 'table'}, 'lineageDetails': details}})
        expected_edges.append((source, target, details))

    def check():
        actual = call('GET', '/pipelines/name/' + quote(pipeline['fullyQualifiedName'], safe='') + '?fields=tasks')
        assert html.unescape(actual['description']) == marker + '\n\n' + description(config)
        assert {t['name']: t.get('downstreamTasks', []) for t in actual['tasks']} == {
            t['name']: t['downstreamTasks'] for t in tasks}
        for source, target, details in expected_edges:
            graph = call('GET', '/lineage/table/' + target['id'] + '?upstreamDepth=1&downstreamDepth=0')
            edge = next(e for e in graph['upstreamEdges'] if e['fromEntity'] == source['id'])
            found = edge['lineageDetails']
            assert found['pipeline']['id'] == pipeline['id']
            assert found['columnsLineage'] == details['columnsLineage']
            assert html.unescape(found['description']) == details['description']
        return actual

    first = check()
    # Negative control: an incorrect expected mapping must fail readback.
    original = expected_edges[0][2]['columnsLineage'][0]['function']
    expected_edges[0][2]['columnsLineage'][0]['function'] = 'deliberately incorrect expectation'
    try:
        check()
    except AssertionError:
        drift_detected = True
    else:
        raise AssertionError('Mapping drift was not detected')
    finally:
        expected_edges[0][2]['columnsLineage'][0]['function'] = original
    for endpoint, name, body in objects:
        call('PUT', endpoint, body)
    repeated = check()
    assert repeated['id'] == first['id'] and repeated['version'] == first['version']
    return {'native_api_verified': True, 'pipelines': 1, 'datasets': len(tables),
            'stages': len(tasks), 'field_lineage_edges': len(expected_edges),
            'mapping_drift_detected': drift_detected, 'repeat_pipeline_version_unchanged': True,
            'control_lanes': len(config['controls']),
            'native_control_lanes': False, 'execution_results_created': 0}


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--config', type=Path, required=True)
    parser.add_argument('--publish', action='store_true')
    args = parser.parse_args()
    config = json.loads(args.config.read_text())
    validate(config)
    if args.publish:
        print(json.dumps(exercise(config, connection()), sort_keys=True))
    else:
        print(json.dumps({'configuration_valid': True}))
