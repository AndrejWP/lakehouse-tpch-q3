import argparse
import random
import statistics
from datetime import datetime, timezone
from common import RESULTS, TABLES, Trino, read, reference, save, write_csv
from validate import compare_query

SCENARIOS = [('PARQUET', 'GZIP'), ('PARQUET', 'ZSTD'), ('ORC', 'ZSTD')]

def benchmark(repeats=5):
    assert repeats >= 5, 'At least five measured runs are required'
    pipeline = read('pipeline.json')
    validation = read('validation.json')
    assert validation['status'] == 'passed' and validation['run_id'] == pipeline['run_id']
    for name in ['benchmark.csv', 'benchmark.json', 'benchmark.md']:
        (RESULTS / name).unlink(missing_ok=True)
    t = Trino()
    expected = t.query(reference())
    output = {'status': 'running', 'run_id': pipeline['run_id'], 'scale': 'sf1',
              'repeats': repeats, 'warmups': 1, 'started_at': datetime.now(timezone.utc).isoformat(),
              'trino_version': t.one('SELECT version()'), 'scenarios': [],
              'method': 'Sequential client monotonic wall time including HTTP/polling; warm cache; no OS/S3 cache reset; verification excluded.'}
    try:
        for fmt, codec in SCENARIOS:
            suffix = '_' + fmt.lower() + '_' + codec.lower()
            scenario = {'format': fmt, 'codec': codec, 'suffix': suffix, 'tables': {}, 'samples': []}
            for name, cols in TABLES.items():
                table = f'lakehouse.benchmark.{name}{suffix}'
                t.query(f'DROP TABLE IF EXISTS {table}')
                t.query(f"CREATE TABLE {table} WITH (format='{fmt}', compression_codec='{codec}') AS SELECT {', '.join(cols)} FROM lakehouse.bronze.{name}")
                write = dict(t.last)
                count = t.one(f'SELECT count(*) FROM {table}')
                # Exact bag equality; this also detects duplicates lost by a checksum collision.
                for left, right in [(table, f'lakehouse.bronze.{name}'), (f'lakehouse.bronze.{name}', table)]:
                    diff = t.one(f'SELECT count(*) FROM ((SELECT * FROM {left}) EXCEPT ALL (SELECT * FROM {right}))')
                    assert diff == 0, f'Benchmark input mismatch: {table}'
                schema = t.query(f'SHOW COLUMNS FROM {table}')
                assert schema == t.query(f'SHOW COLUMNS FROM lakehouse.bronze.{name}')
                definition = t.one(f'SHOW CREATE TABLE {table}')
                assert fmt in definition and codec in definition, definition
                metrics = t.metrics(table)
                assert metrics['file_count'] > 0 and all(f[2] == fmt for f in metrics['files'])
                scenario['tables'][name] = {'rows': count, 'write': write, 'definition': definition, **metrics}
            query = reference('lakehouse.benchmark', suffix)
            got = t.query(query)
            scenario['warmup'] = dict(t.last)
            compare_query(t, got, expected, reference())
            output['scenarios'].append(scenario)
        # Interleave configurations in a deterministic shuffled order to reduce order bias.
        rng = random.Random(1)
        output['measurement_order'] = []
        for repetition in range(repeats):
            ordered = list(output['scenarios'])
            rng.shuffle(ordered)
            for s in ordered:
                got = t.query(reference('lakehouse.benchmark', s['suffix']))
                sample = dict(t.last)
                s['samples'].append(sample)
                output['measurement_order'].append([repetition + 1, s['suffix']])
                compare_query(t, got, expected, reference())
        for s in output['scenarios']:
            timings = [x['wall_seconds'] for x in s['samples']]
            s.update(rows=sum(x['rows'] for x in s['tables'].values()),
                     data_bytes=sum(x['data_bytes'] for x in s['tables'].values()),
                     file_count=sum(x['file_count'] for x in s['tables'].values()),
                     write_seconds=sum(x['write']['wall_seconds'] for x in s['tables'].values()),
                     median_seconds=statistics.median(timings), min_seconds=min(timings), max_seconds=max(timings))
            s['size_mib'] = s['data_bytes'] / 1048576
        a, b = output['scenarios'][:2]
        output['comparison_parquet_zstd_vs_gzip'] = {
            'baseline': 'PARQUET GZIP',
            'size_saving_percent': (a['data_bytes'] - b['data_bytes']) / a['data_bytes'] * 100,
            'query_time_change_percent': (b['median_seconds'] - a['median_seconds']) / a['median_seconds'] * 100,
            'write_time_change_percent': (b['write_seconds'] - a['write_seconds']) / a['write_seconds'] * 100}
        output['status'] = 'passed'
        fields = ['format', 'codec', 'rows', 'data_bytes', 'size_mib', 'file_count', 'write_seconds', 'median_seconds', 'min_seconds', 'max_seconds']
        write_csv('benchmark.csv', fields, [[s[f] for f in fields] for s in output['scenarios']])
        md = '| Format | Codec | Rows | Size MiB | Write s | Query median s | Min s | Max s | Files |\n|---|---|---:|---:|---:|---:|---:|---:|---:|\n'
        for s in output['scenarios']:
            md += f"| {s['format']} | {s['codec']} | {s['rows']} | {s['size_mib']:.3f} | {s['write_seconds']:.3f} | {s['median_seconds']:.3f} | {s['min_seconds']:.3f} | {s['max_seconds']:.3f} | {s['file_count']} |\n"
        (RESULTS / 'benchmark.md').write_text(md)
    except Exception as exc:
        output.update(status='failed', error=str(exc))
        raise
    finally:
        output['queries'] = t.audit
        save('benchmark.json', output)
    print('Three physical sf1 scenarios, warmup + five runs: verified')

if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--repeats', type=int, default=5)
    benchmark(p.parse_args().repeats)
