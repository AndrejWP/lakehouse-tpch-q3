import argparse
import math
from common import RESULTS, TABLES, Trino, read, reference, save, sql, write_csv

REL_TOL = 1e-10
ABS_TOL = 1e-6

def close(a, b):
    return math.isfinite(a) and math.isfinite(b) and math.isclose(a, b, rel_tol=REL_TOL, abs_tol=ABS_TOL)

def key(row):
    return row[0], row[2], row[3]

def compare(actual, expected, candidates=None):
    assert len(actual) == len(expected) == 10, 'Q3 must return ten rows'
    assert len({key(r) for r in actual}) == 10, 'Duplicate Gold order keys'
    assert len({r[0] for r in actual}) == 10, 'Repeated orderkey'
    assert all(all(v is not None for v in r) and r[1] >= 0 and math.isfinite(r[1]) for r in actual)
    a, e = {key(r): r[1] for r in actual}, {key(r): r[1] for r in expected}
    if a.keys() == e.keys():
        assert all(close(a[k], e[k]) for k in a), f'Revenue mismatch: {actual}, {expected}'
        return
    assert candidates is not None, 'Different top-10 keys; boundary ties must be verified'
    pool = {key(r): r[1] for r in candidates}
    cutoff = min(e.values())
    required = {k for k, v in pool.items() if v > cutoff and not close(v, cutoff)}
    assert required <= a.keys(), 'Missing strictly higher revenue order'
    assert all(k in pool and close(v, pool[k]) and (v >= cutoff or close(v, cutoff)) for k, v in a.items()), 'Invalid boundary tie'
    assert all(close(v, cutoff) for k, v in a.items() if k not in e), 'Difference is not a boundary tie'

def compare_query(t, actual, expected, query):
    if {key(r) for r in actual} != {key(r) for r in expected}:
        aggregate = query.rsplit('ORDER BY', 1)[0]
        # Rare tie at rank 10: retrieve all aggregates and validate eligible membership.
        compare(actual, expected, t.query(aggregate))
    else:
        compare(actual, expected)

def fingerprints(t):
    result = {f'bronze.{n}': t.fingerprint(f'lakehouse.bronze.{n}', c) for n, c in TABLES.items()}
    result['silver.shipping_order_lines'] = t.fingerprint('lakehouse.silver.shipping_order_lines',
        ['orderkey', 'orderdate', 'shippriority', 'shipdate', 'extendedprice', 'discount', 'line_revenue', 'mktsegment'])
    result['gold'] = sorted(t.query('SELECT * FROM lakehouse.gold.shipping_priority'))
    return result

def validate(rerun=False):
    run = read('pipeline.json')
    t = Trino()
    result = {'status': 'failed', 'run_id': run['run_id'], 'scale': 'sf1'}
    try:
        quality = dict(t.file('05_validation.sql')[0])
        assert not any(quality.values()), f'Quality violations: {quality}'
        counts = {}
        for name, cols in TABLES.items():
            a = t.fingerprint(f'tpch.sf1.{name}', cols)
            b = t.fingerprint(f'lakehouse.bronze.{name}', cols)
            assert a == b, f'Source/Bronze mismatch: {name}'
            types_a = [(r[0], r[1]) for r in t.query(f'SHOW COLUMNS FROM tpch.sf1.{name}') if r[0] in cols]
            types_b = [(r[0], r[1]) for r in t.query(f'SHOW COLUMNS FROM lakehouse.bronze.{name}')]
            # Iceberg stores varchar without the source's length bound; values stay unchanged.
            normalize = lambda rows: sorted((n, 'varchar' if ty.startswith('varchar') else ty) for n, ty in rows)
            assert normalize(types_a) == normalize(types_b), f'Type mismatch {name}'
            counts[name] = b
        # EXCEPT ALL verifies full Silver row multiplicities, including legitimate repeated projections.
        definition = sql('02_silver.sql').split(' AS\n', 1)[1]
        silver = 'SELECT * FROM lakehouse.silver.shipping_order_lines'
        for left, right in [(definition, silver), (silver, definition)]:
            assert t.one(f'SELECT count(*) FROM (({left}) EXCEPT ALL ({right}))') == 0, 'Silver rows differ'
        raw_sum = t.one(f'SELECT sum(line_revenue) FROM ({definition})')
        silver_sum = t.one('SELECT sum(line_revenue) FROM lakehouse.silver.shipping_order_lines')
        assert close(raw_sum, silver_sum), 'Silver total revenue changed'
        assert t.one('SELECT count(*) FROM lakehouse.gold.shipping_priority') == 10, 'Gold has extra or missing rows'
        gold = t.query('SELECT orderkey, revenue, orderdate, shippriority FROM lakehouse.gold.shipping_priority ORDER BY revenue DESC LIMIT 10')
        expected = t.query(reference())
        compare_query(t, gold, expected, reference())
        rerun_result = {'status': 'not_run', 'command': 'make validate-rerun'}
        old_path = RESULTS / 'validation.json'
        if old_path.exists():
            old = read('validation.json')
            if old.get('run_id') == run['run_id'] and old.get('status') == 'passed':
                rerun_result = old.get('rerun', rerun_result)
        if rerun:
            before = fingerprints(t)
            from run_pipeline import pipeline
            pipeline()
            after = fingerprints(t)
            # Double summation order can change across runs; compare Gold using tolerance.
            compare(after.pop('gold'), before.pop('gold'))
            assert before == after, 'Pipeline rerun changed row multiplicities or data'
            run = read('pipeline.json')
            result['run_id'] = run['run_id']
            rerun_result = {'status': 'passed', 'fingerprints': after}
            gold = t.query('SELECT * FROM lakehouse.gold.shipping_priority ORDER BY revenue DESC')
            compare_query(t, gold, expected, reference())
        physical = {}
        for table in ['bronze.customer', 'bronze.orders', 'bronze.lineitem', 'silver.shipping_order_lines', 'gold.shipping_priority']:
            m = t.metrics('lakehouse.' + table)
            assert m['data_bytes'] > 0 and m['file_count'] > 0
            assert all(r[0].startswith('s3://lakehouse/') and r[2] == 'PARQUET' for r in m['files'])
            physical[table] = m
        result.update(status='passed', counts=counts, quality=quality, reference=expected,
                      gold=gold, source_line_revenue=raw_sum, silver_line_revenue=silver_sum,
                      rerun=rerun_result, physical=physical, rel_tol=REL_TOL, abs_tol=ABS_TOL)
        write_csv('q3_result.csv', ['orderkey', 'revenue', 'orderdate', 'shippriority'], gold)
    except Exception as exc:
        result['error'] = str(exc)
        raise
    finally:
        result['queries'] = t.audit
        save('validation.json', result)
    print('Q3, Bronze fidelity, Silver multiplicities and physical files verified')

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--rerun', action='store_true')
    validate(parser.parse_args().rerun)
