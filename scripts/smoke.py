import json
from urllib.parse import urlsplit
from common import ROOT, Trino, read, save
from validate import validate

def smoke():
    t = Trino()
    catalogs = {r[0] for r in t.query('SHOW CATALOGS')}
    assert {'tpch', 'lakehouse'} <= catalogs
    assert t.one('SELECT count(*) FROM tpch.tiny.customer') > 0
    previous = read('validation.json')
    assert previous.get('rerun', {}).get('status') == 'passed', 'Run make validate-rerun first'
    validate()
    assert t.one('SELECT count(*) FROM lakehouse.gold.shipping_priority') == 10
    run = read('pipeline.json')['run_id']
    for name in ['bootstrap.json', 'validation.json', 'benchmark.json', 'iceberg_demo.json', 'bi.json']:
        evidence = read(name)
        assert evidence['status'] == 'passed', f'{name} did not pass'
        if 'run_id' in evidence:
            assert evidence['run_id'] == run, f'Stale evidence: {name}'
    objects = [json.loads(line) for line in (ROOT / 'evidence/minio-objects.ndjson').read_text().splitlines() if line.strip()]
    assert objects and all(obj.get('status') == 'success' for obj in objects), 'MinIO listing failed'
    sizes = {obj['key']: obj['size'] for obj in objects if obj.get('type') == 'file'}
    checked = 0
    for metrics in read('validation.json')['physical'].values():
        for path, size, fmt in metrics['files']:
            key = urlsplit(path).path.lstrip('/')
            assert sizes.get(key) == size, f'MinIO object missing or wrong size: {key}'
            checked += 1
    save('smoke.json', {'status': 'passed', 'run_id': run, 's3_files_checked': checked, 'queries': t.audit})
    print('All mandatory smoke checks passed')

if __name__ == '__main__':
    smoke()
