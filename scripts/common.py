"""Small synchronous Trino HTTP client; no third-party runtime dependencies."""
import csv
import json
import os
import re
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / 'results'
TABLES = {
    'customer': ['custkey', 'mktsegment'],
    'orders': ['orderkey', 'custkey', 'orderdate', 'shippriority'],
    'lineitem': ['orderkey', 'extendedprice', 'discount', 'shipdate'],
}

def save(name, data):
    RESULTS.mkdir(exist_ok=True)
    dest = RESULTS / name
    tmp = dest.with_suffix(dest.suffix + '.tmp')
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False) + '\n')
    tmp.replace(dest)

def read(name):
    return json.loads((RESULTS / name).read_text())

def sql(name):
    return (ROOT / 'sql' / name).read_text().strip().rstrip(';')

def statements(text):
    # Project SQL deliberately has no semicolons within quoted strings.
    text = re.sub(r'--[^\n]*', '', text)
    return [s.strip() for s in text.split(';') if s.strip()]

def http(url, data=None, method=None, headers=None):
    raw = None if data is None else json.dumps(data).encode()
    req = urllib.request.Request(url, data=raw, method=method,
                                 headers={'Content-Type': 'application/json', **(headers or {})})
    with urllib.request.urlopen(req, timeout=60) as response:
        payload = response.read()
        return json.loads(payload) if payload else {}

class Trino:
    def __init__(self):
        self.url = os.environ.get('TRINO_URL', 'http://localhost:8080').rstrip('/')
        self.audit = []
        self.last = {}

    def query(self, statement):
        start = time.perf_counter()
        headers = {'X-Trino-User': 'lakehouse', 'X-Trino-Source': 'practical-q3',
                   'X-Trino-Catalog': 'lakehouse', 'X-Trino-Schema': 'bronze'}
        request = urllib.request.Request(self.url + '/v1/statement',
                                         data=statement.encode(), headers=headers)
        rows, columns, next_uri = [], [], None
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                page = json.load(response)
            deadline = time.monotonic() + 1900
            while True:
                next_uri = page.get('nextUri')
                if 'error' in page:
                    err = page['error']
                    raise RuntimeError(f"Trino {page.get('id')}: {err.get('errorName')}: {err.get('message')}")
                columns = page.get('columns', columns)
                rows.extend(page.get('data', []))
                if not next_uri:
                    break
                if time.monotonic() > deadline:
                    raise TimeoutError('Trino query exceeded 1900 seconds')
                time.sleep(0.03)
                with urllib.request.urlopen(urllib.request.Request(next_uri, headers=headers), timeout=60) as response:
                    page = json.load(response)
            self.last = {'query_id': page.get('id'), 'wall_seconds': time.perf_counter() - start,
                         'stats': page.get('stats', {}), 'columns': columns}
            self.audit.append({'sql': statement, **self.last})
            return rows
        except BaseException:
            if next_uri:
                # Cancel pending work; preserve original exception if cancellation also fails.
                try:
                    urllib.request.urlopen(urllib.request.Request(next_uri, method='DELETE', headers=headers), timeout=5).close()
                except (OSError, urllib.error.URLError):
                    pass
            raise

    def one(self, statement):
        rows = self.query(statement)
        if len(rows) != 1 or len(rows[0]) != 1:
            raise AssertionError(f'Expected scalar: {rows}')
        return rows[0][0]

    def file(self, name):
        return [self.query(s) for s in statements(sql(name))]

    def fingerprint(self, table, columns):
        expr = ', '.join(columns)
        rows = self.query(f'SELECT count(*), to_hex(checksum(ROW({expr}))) FROM {table}')
        return {'rows': rows[0][0], 'checksum': rows[0][1]}

    def files(self, table):
        namespace, name = table.rsplit('.', 1)
        return self.query(f'SELECT file_path, file_size_in_bytes, file_format FROM {namespace}."{name}$files" WHERE content = 0 ORDER BY file_path')

    def metrics(self, table):
        files = self.files(table)
        return {'data_bytes': sum(r[1] for r in files), 'file_count': len(files),
                'size_mib': sum(r[1] for r in files) / 1048576, 'files': files}

def reference(prefix='tpch.sf1', suffix=''):
    text = sql('04_reference_q3.sql')
    for name in TABLES:
        text = text.replace(f'tpch.sf1.{name}', f'{prefix}.{name}{suffix}')
    return text

def write_csv(name, columns, rows):
    with (RESULTS / name).open('w', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(columns)
        writer.writerows(rows)
