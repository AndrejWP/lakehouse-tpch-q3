import argparse
import json
import os
import time
import urllib.error
from common import Trino, http, save

NIL = '00000000-0000-0000-0000-000000000000'

def catalog():
    base = os.environ.get('LAKEKEEPER_URL', 'http://localhost:8181') + '/management/v1'
    try:
        http(base + '/bootstrap', {'accept-terms-of-use': True})
    except urllib.error.HTTPError as e:
        payload = json.loads(e.read())
        if e.code != 400 or payload.get('error', {}).get('type') != 'CatalogAlreadyBootstrapped':
            raise
    listing = http(base + '/warehouse', headers={'x-project-id': NIL})
    warehouses = [w for w in listing.get('warehouses', []) if w['name'] == 'local']
    if warehouses:
        profile = warehouses[0]['storage-profile']
        assert profile['bucket'] == 'lakehouse' and profile['endpoint'].rstrip('/') == 'http://minio:9000', 'Existing Warehouse has an incompatible storage profile'
    if not warehouses:
        http(base + '/warehouse', {
            'warehouse-name': 'local', 'project-id': NIL,
            'storage-profile': {'type': 's3', 'bucket': 'lakehouse', 'key-prefix': 'warehouse',
                                'endpoint': 'http://minio:9000', 'region': 'local-01',
                                'path-style-access': True, 'flavor': 'minio', 'sts-enabled': False},
            'storage-credential': {'type': 's3', 'credential-type': 'access-key',
                                   'aws-access-key-id': os.environ['MINIO_ROOT_USER'],
                                   'aws-secret-access-key': os.environ['MINIO_ROOT_PASSWORD']}})
    print('Lakekeeper warehouse local ready')

def bootstrap():
    t = Trino()
    deadline = time.monotonic() + 180
    while True:
        try:
            t.one('SELECT 1')
            break
        except (OSError, RuntimeError):
            if time.monotonic() > deadline:
                raise
            time.sleep(2)
    for ns in ['bronze', 'silver', 'gold', 'benchmark', 'demo']:
        t.query(f'CREATE SCHEMA IF NOT EXISTS lakehouse.{ns}')
    t.query('DROP TABLE IF EXISTS lakehouse.demo.storage_probe')
    t.query("CREATE TABLE lakehouse.demo.storage_probe WITH (format='PARQUET', compression_codec='ZSTD') AS SELECT CAST(42 AS bigint) AS value")
    assert t.one('SELECT sum(value) FROM lakehouse.demo.storage_probe') == 42
    metrics = t.metrics('lakehouse.demo.storage_probe')
    assert metrics['data_bytes'] > 0 and metrics['file_count'] > 0
    assert all(r[0].startswith('s3://lakehouse/') for r in metrics['files'])
    save('bootstrap.json', {'status': 'passed', 'probe': metrics, 'queries': t.audit})
    print('Iceberg write/read on MinIO verified')

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--catalog-only', action='store_true')
    args = parser.parse_args()
    if args.catalog_only:
        catalog()
    else:
        bootstrap()
