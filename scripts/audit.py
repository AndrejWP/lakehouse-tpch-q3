"""Non-destructive submission audit: saved measurements, docs, Git candidates and live copies."""
import argparse
import csv
import hashlib
import json
import math
import os
import re
import statistics
import subprocess
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import unquote, urlsplit
from common import ROOT, RESULTS, TABLES, Trino, read, reference, save
from validate import compare_query

BENCHMARK_FILES = ['benchmark.csv', 'benchmark.json', 'benchmark.md']
SCENARIOS = [('PARQUET', 'GZIP'), ('PARQUET', 'ZSTD'), ('ORC', 'ZSTD')]


def forbidden(path):
    p = Path(path)
    return (any(part in {'.git', '.venv', '__MACOSX', '__pycache__', '.pytest_cache', 'dist', '.AppleDouble', 'htmlcov'} for part in p.parts)
            or p.name in {'.DS_Store', '.LSOverride', '.coverage'} or p.name.startswith('._')
            or (p.name.startswith('.env') and p.name != '.env.example')
            or p.suffix in {'.pyc', '.pyo', '.log', '.tmp', '.swp', '.swo', '.pem', '.key'} or p.name.endswith('~'))


def git_files(*args):
    data = subprocess.check_output(['git', 'ls-files', '-z', *args], cwd=ROOT)
    return sorted(set(p.decode() for p in data.split(b'\0') if p))


def publication_files():
    if not (ROOT / '.git').exists():
        files = []
        for folder, directories, names in os.walk(ROOT):
            directories[:] = [d for d in directories if not forbidden((Path(folder) / d).relative_to(ROOT))]
            for name in names:
                path = Path(folder) / name
                relative = path.relative_to(ROOT)
                if not forbidden(relative):
                    assert not path.is_symlink(), f'Symlink in submission: {relative}'
                    files.append(str(relative))
        return sorted(files)
    tracked = git_files('--cached')
    assert not any(forbidden(p) for p in tracked), 'Private or generated files are tracked by Git'
    files = git_files('--cached', '--others', '--exclude-standard')
    assert not any(forbidden(p) for p in files), 'Private or generated files would enter publication'
    assert all(not (ROOT / p).is_symlink() for p in files), 'Publication must not dereference symlinks'
    return files


def verify_benchmark(data):
    assert data['status'] == 'passed' and data['scale'] == 'sf1'
    assert data['repeats'] == 5 and data['warmups'] == 1
    assert [(s['format'], s['codec']) for s in data['scenarios']] == SCENARIOS
    audit = {q['query_id']: q for q in data['queries']}
    for s in data['scenarios']:
        assert len(s['samples']) == 5
        timings = [x['wall_seconds'] for x in s['samples']]
        expected = {'median_seconds': statistics.median(timings), 'min_seconds': min(timings), 'max_seconds': max(timings),
                    'write_seconds': sum(t['write']['wall_seconds'] for t in s['tables'].values()),
                    'data_bytes': sum(t['data_bytes'] for t in s['tables'].values()),
                    'file_count': sum(t['file_count'] for t in s['tables'].values()),
                    'rows': sum(t['rows'] for t in s['tables'].values())}
        expected['size_mib'] = expected['data_bytes'] / 1048576
        for key, value in expected.items():
            assert math.isclose(s[key], value, rel_tol=1e-12, abs_tol=1e-12), f'{s["suffix"]}: incorrect {key}'
        assert s['suffix'] == '_' + s['format'].lower() + '_' + s['codec'].lower()
        for sample in [s['warmup'], *s['samples']]:
            q = audit[sample['query_id']]
            assert q['sql'] == reference('lakehouse.benchmark', s['suffix'])
            assert q['wall_seconds'] == sample['wall_seconds'] > 0
        assert set(s['tables']) == set(TABLES)
        for name, t in s['tables'].items():
            assert t['data_bytes'] == sum(f[1] for f in t['files'])
            assert t['file_count'] == len(t['files']) > 0
            assert all(f[2] == s['format'] for f in t['files'])
            assert t['write']['wall_seconds'] == audit[t['write']['query_id']]['wall_seconds'] > 0
            assert f"compression_codec = '{s['codec']}'" in t['definition']
    a, b = data['scenarios'][:2]
    expected = {
        'size_saving_percent': (a['data_bytes'] - b['data_bytes']) / a['data_bytes'] * 100,
        'query_time_change_percent': (b['median_seconds'] - a['median_seconds']) / a['median_seconds'] * 100,
        'write_time_change_percent': (b['write_seconds'] - a['write_seconds']) / a['write_seconds'] * 100}
    for k, value in expected.items():
        assert math.isclose(data['comparison_parquet_zstd_vs_gzip'][k], value, rel_tol=1e-12, abs_tol=1e-12), k
    return expected


def check_documents(files):
    links = 0
    for name in files:
        if not name.endswith('.md'):
            continue
        p = ROOT / name
        text = p.read_text()
        assert not re.search(r'\b(?:TODO|TBD)\b|\[ФИО[^\]]*\]', text), f'Unfilled field in {name}'
        for target in re.findall(r'!?\[[^\]]*\]\(([^)]+)\)', text):
            target = target.strip('<>')
            url = urlsplit(target)
            if url.scheme or target.startswith('#'):
                continue
            path = (p.parent / unquote(url.path)).resolve()
            assert path.is_relative_to(ROOT) and path.exists(), f'Broken local link: {name}: {target}'
            links += 1
    text = (ROOT / 'report.md').read_text()
    assert '| ФИО | Потрикеев Андрей |' in text
    assert re.findall(r'^## (\d)\.', text, re.M) == list('1234567')
    assert '### 6.1.' in text and '### 6.2.' in text
    conclusion = text.split('## 7. Выводы', 1)[1].strip()
    assert 3 <= len(re.split(r'(?<=[.!?])\s+', conclusion)) <= 5
    assert not any(term in text for term in ['не измерено', 'не подтверждён', 'ещё не выполнен'])
    return links


def security(files):
    env = dict(line.split('=', 1) for line in (ROOT / '.env').read_text().splitlines() if line and not line.startswith('#'))
    template = dict(line.split('=', 1) for line in (ROOT / '.env.example').read_text().splitlines() if line and not line.startswith('#'))
    required = set(re.findall(r'\$\{([A-Z_]+)', (ROOT / 'docker-compose.yml').read_text()))
    assert required <= template.keys(), 'Missing variable in .env.example'
    secret_values = [v.encode() for k, v in env.items() if any(part in k for part in ['PASSWORD', 'SECRET', 'TOKEN', 'ENCRYPTION']) and v]
    for name in files:
        p = ROOT / name
        contents = [p.read_bytes()]
        if p.suffix == '.zip':
            with zipfile.ZipFile(p) as z:
                assert not any(forbidden(n) for n in z.namelist()), f'Private file in ZIP {name}'
                contents.extend(z.read(n) for n in z.namelist())
        assert not any(value in content for value in secret_values for content in contents), f'Secret in publishable file: {name}'
    return {'files_scanned': len(files), 'tracked_private_files': 0, 'secret_values_found': 0,
            'env_example_variables': sorted(template)}


def runtime(data):
    t = Trino()
    expected = t.query(reference())
    records = []
    for s in data['scenarios']:
        for name in TABLES:
            table = f'lakehouse.benchmark.{name}{s["suffix"]}'
            stored = s['tables'][name]
            assert t.files(table) == stored['files'], f'Active files changed since benchmark: {table}'
            assert t.one(f'SELECT count(*) FROM {table}') == stored['rows']
            assert t.query(f'SHOW COLUMNS FROM {table}') == t.query(f'SHOW COLUMNS FROM lakehouse.bronze.{name}')
            assert t.one(f'SHOW CREATE TABLE {table}') == stored['definition']
            for left, right in [(table, f'lakehouse.bronze.{name}'), (f'lakehouse.bronze.{name}', table)]:
                assert t.one(f'SELECT count(*) FROM ((SELECT * FROM {left}) EXCEPT ALL (SELECT * FROM {right}))') == 0, table
        got = t.query(reference('lakehouse.benchmark', s['suffix']))
        compare_query(t, got, expected, reference())
        records.append({'format': s['format'], 'codec': s['codec'], 'input_equality': 'passed', 'q3': 'passed'})
    return {'status': 'passed', 'scenarios': records, 'queries': t.audit,
            'note': 'Only correctness and current metadata verified; original performance measurements were not replaced.'}


def audit(live=False):
    data = read('benchmark.json')
    run = read('pipeline.json')['run_id']
    result = {'status': 'failed', 'run_id': run, 'checked_at': datetime.now(timezone.utc).isoformat()}
    try:
        hashes = {name: hashlib.sha256((RESULTS / name).read_bytes()).hexdigest() for name in BENCHMARK_FILES}
        result['benchmark_comparison'] = verify_benchmark(data)
        assert data['run_id'] == run
        with (RESULTS / 'benchmark.csv').open(newline='') as f:
            rows = list(csv.DictReader(f))
        assert len(rows) == 3
        for row, scenario in zip(rows, data['scenarios']):
            for field, value in row.items():
                if field in {'format', 'codec'}:
                    assert value == scenario[field]
                else:
                    assert math.isclose(float(value), scenario[field], rel_tol=1e-12, abs_tol=1e-12), field
            md_row = f"| {scenario['format']} | {scenario['codec']} | {scenario['rows']} | {scenario['size_mib']:.3f} | {scenario['write_seconds']:.3f} | {scenario['median_seconds']:.3f} |"
            assert md_row in (RESULTS / 'benchmark.md').read_text()
        files = publication_files()
        result['security'] = security(files)
        result['local_markdown_links'] = check_documents(files)
        for name in ['validation.json', 'iceberg_demo.json', 'bi.json', 'smoke.json']:
            evidence = read(name)
            assert evidence['status'] == 'passed' and evidence['run_id'] == run, name
        result['runtime'] = runtime(data) if live else {'status': 'not_run', 'command': 'make audit-runtime'}
        assert hashes == {name: hashlib.sha256((RESULTS / name).read_bytes()).hexdigest() for name in BENCHMARK_FILES}
        result.update(status='passed', benchmark_files_sha256=hashes,
                      make_all='Not executed: it rebuilds tables and overwrites saved measurements. Separate targets verified.')
    except Exception as exc:
        result['error'] = str(exc)
        raise
    finally:
        save('final_audit.json', result)
    print('Submission audit passed; benchmark files unchanged')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--runtime', action='store_true')
    audit(parser.parse_args().runtime)
