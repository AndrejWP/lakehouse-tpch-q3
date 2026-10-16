"""Offline syntax checks. Passing does not imply a running Lakehouse."""
import ast
import json
import re
from pathlib import Path
import sqlglot
import yaml
from sqlglot import exp
from sqlglot.errors import ErrorLevel
from common import ROOT, reference, save, sql, statements

checks = []
for path in sorted(ROOT.rglob('*.py')):
    if '.venv' in path.parts or '.git' in path.parts:
        continue
    ast.parse(path.read_text(), filename=str(path))
    checks.append(str(path.relative_to(ROOT)))
compose = yaml.safe_load((ROOT / 'docker-compose.yml').read_text())
for name, service in compose['services'].items():
    image = service.get('image', '')
    assert ':' in image and not image.endswith(':latest'), (name, image)
    assert 'platform' not in service, 'Do not silently emulate ARM64'
assert compose['services']['trino']['depends_on']['catalog-init']['condition'] == 'service_completed_successfully'
assert compose['services']['superset']['depends_on']['superset-init']['condition'] == 'service_completed_successfully'
counts = {}
for path in sorted((ROOT / 'sql').glob('*.sql')):
    statements_ = statements(path.read_text().replace(':snapshot_id', '123456789'))
    for s in statements_:
        tree = sqlglot.parse_one(s, read='trino', error_level=ErrorLevel.RAISE)
        # ALTER ... EXECUTE is a Trino connector procedure; sqlglot leaves it as Command.
        if isinstance(tree, exp.Command):
            assert re.match(r'ALTER TABLE .* EXECUTE rollback_to_snapshot', s, re.I), s
    counts[path.name] = len(statements_)
for fmt, codec in [('PARQUET', 'GZIP'), ('PARQUET', 'ZSTD'), ('ORC', 'ZSTD')]:
    sqlglot.parse_one(reference('lakehouse.benchmark', '_' + fmt.lower() + '_' + codec.lower()), read='trino')
for statement in statements(sql('01_bronze.sql')):
    if statement.startswith('CREATE'):
        tree = sqlglot.parse_one(statement, read='trino')
        assert tree.find(exp.Select).args.get('where') is None, 'Bronze must not filter rows'
assert 'LIMIT' not in sql('02_silver.sql')
assert 'DISTINCT' not in sql('02_silver.sql')
for filename in ['01_bronze.sql', '02_silver.sql', '03_gold.sql', '06_schema_evolution.sql', '07_time_travel.sql']:
    for statement in statements(sql(filename)):
        if statement.startswith('CREATE TABLE'):
            assert 'compression_codec=' in statement and 'format=' in statement
save('static_checks.json', {'status': 'passed', 'python_files': len(checks), 'sql_statements': counts,
                           'services': list(compose['services']),
                           'limitation': 'Syntax/configuration checks only; connector procedures require live Trino.'})
print(json.dumps({'python_files': len(checks), 'sql_statements': counts, 'status': 'passed'}, ensure_ascii=False))
