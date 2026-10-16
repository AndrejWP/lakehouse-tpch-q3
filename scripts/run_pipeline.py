import argparse
import uuid
from datetime import datetime, timezone
from common import RESULTS, TABLES, Trino, save

OUTPUTS = ['benchmark.csv', 'benchmark.json', 'benchmark.md', 'validation.json',
           'q3_result.csv', 'metrics.json', 'iceberg_demo.json', 'bi.json', 'pipeline.json', 'smoke.json']

def pipeline():
    # Invalidate prior evidence before any table changes, including a failed rebuild.
    for name in OUTPUTS:
        (RESULTS / name).unlink(missing_ok=True)
    t = Trino()
    t.file('01_bronze.sql')
    quality = dict(t.file('05_validation.sql')[0])
    assert not any(quality.values()), f'Bronze quality violations: {quality}'
    for name, cols in TABLES.items():
        source = t.fingerprint(f'tpch.sf1.{name}', cols)
        bronze = t.fingerprint(f'lakehouse.bronze.{name}', cols)
        assert source == bronze, f'{name}: source/Bronze differ: {source}, {bronze}'
    t.file('02_silver.sql')
    t.file('03_gold.sql')
    save('pipeline.json', {'run_id': str(uuid.uuid4()), 'scale': 'sf1',
                          'completed_at': datetime.now(timezone.utc).isoformat(),
                          'quality': quality, 'queries': t.audit})
    print('TPC-H sf1 → Bronze → Silver → Gold complete')

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.parse_args()
    pipeline()
