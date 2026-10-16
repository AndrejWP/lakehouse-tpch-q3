"""Authenticate to Superset and execute actual synchronous SQL Lab queries."""
import http.cookiejar
import json
import os
import urllib.request
import uuid
from common import ROOT, RESULTS, Trino, read, save, sql, statements

def check():
    (RESULTS / 'bi.json').unlink(missing_ok=True)
    base = os.environ.get('SUPERSET_URL', 'http://localhost:8088')
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
    token, csrf = None, None
    def request(path, payload=None, archive=None):
        headers = {'Content-Type': 'application/json', 'Referer': base + '/'}
        if token:
            headers['Authorization'] = 'Bearer ' + token
        if csrf:
            headers['X-CSRFToken'] = csrf
        if archive is not None:
            boundary = 'lakehouse-' + uuid.uuid4().hex
            headers['Content-Type'] = 'multipart/form-data; boundary=' + boundary
            body = (f'--{boundary}\r\nContent-Disposition: form-data; name="overwrite"\r\n\r\ntrue\r\n'
                    f'--{boundary}\r\nContent-Disposition: form-data; name="formData"; filename="q3-chart.zip"\r\n'
                    'Content-Type: application/zip\r\n\r\n').encode() + archive + f'\r\n--{boundary}--\r\n'.encode()
        else:
            body = None if payload is None else json.dumps(payload).encode()
        req = urllib.request.Request(base + path, data=body, headers=headers)
        with opener.open(req, timeout=330) as response:
            return json.load(response)
    auth = request('/api/v1/security/login', {'username': os.environ['SUPERSET_ADMIN_USER'],
         'password': os.environ['SUPERSET_ADMIN_PASSWORD'], 'provider': 'db', 'refresh': True})
    token = auth['access_token']
    csrf = request('/api/v1/security/csrf_token/')['result']
    databases = request('/api/v1/database/')['result']
    database = next(d for d in databases if d['database_name'] == 'Lakehouse Trino')
    evidence = []
    t = Trino()
    for statement in statements(sql('08_bi_queries.sql')):
        result = request('/api/v1/sqllab/execute/', {'database_id': database['id'], 'sql': statement,
                         'schema': 'bronze', 'runAsync': False, 'expand_data': True, 'queryLimit': 1000})
        assert result.get('status') == 'success', result
        data = result.get('data', [])
        assert data, 'SQL Lab returned no data'
        expected = t.query(statement)
        column_names = [c['name'] for c in t.last['columns']]
        assert sorted([[row[n] for n in column_names] for row in data]) == sorted(expected), 'SQL Lab/Trino mismatch'
        evidence.append({'sql': statement, 'data': data, 'query': result.get('query'), 'status': result['status']})
    imported = request('/api/v1/chart/import/', archive=(ROOT / 'docker/superset/q3-chart.zip').read_bytes())
    assert imported.get('message') == 'OK', imported
    charts = request('/api/v1/chart/')['result']
    chart = [c for c in charts if c['slice_name'] == 'TPC-H Q3 — Top 10 заказов по выручке']
    assert len(chart) == 1, 'Chart import must be idempotent'
    detail = request(f"/api/v1/chart/{chart[0]['id']}")['result']
    params = json.loads(detail['params'])
    assert params['viz_type'] == 'echarts_timeseries_bar' and params['x_axis'] == 'orderkey'
    assert params['xAxisForceCategorical'] is True
    assert params['x_axis_sort'] == 'MAX(revenue)' and params['x_axis_sort_asc'] is False
    assert len(params['metrics']) == 1
    metric = params['metrics'][0]
    assert metric['aggregate'] == 'MAX' and metric['column']['column_name'] == 'revenue'
    dataset_id = int(params['datasource'].split('__')[0])
    dataset = request(f'/api/v1/dataset/{dataset_id}')['result']
    assert 'lakehouse.gold.shipping_priority' in dataset['sql'], 'Chart is not based on physical Gold'
    save('bi.json', {'status': 'passed', 'run_id': read('pipeline.json')['run_id'],
                     'database_id': database['id'], 'engine': 'trino', 'sql_lab': evidence,
                     'gold_chart': {'id': chart[0]['id'], 'name': chart[0]['slice_name'], 'import_status': 'passed', 'parameters_verified': True,
                                    'x_axis': 'orderkey', 'metric': 'MAX(revenue)', 'sort': 'descending',
                                    'source_sql': dataset['sql']}})
    print('Superset SQL Lab reads Bronze and Gold through Trino')

if __name__ == '__main__':
    check()
