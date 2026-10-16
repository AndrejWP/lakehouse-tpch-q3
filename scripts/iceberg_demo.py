from common import RESULTS, Trino, read, save, sql, statements

def demo():
    (RESULTS / 'iceberg_demo.json').unlink(missing_ok=True)
    t = Trino()
    evolution = 'lakehouse.demo.shipping_lines_evolution'
    commands = statements(sql('06_schema_evolution.sql'))
    t.query(commands[0]); t.query(commands[1])
    before_schema = t.query(commands[2])
    before_files = t.files(evolution)
    before = t.fingerprint(evolution, ['orderkey', 'shipdate', 'line_revenue'])
    t.query(commands[3]); t.query(commands[4])
    after_schema = t.query(commands[5])
    after = t.fingerprint(evolution, ['orderkey', 'shipdate', 'line_revenue'])
    after_files = t.files(evolution)
    nulls = t.query(commands[6])[0]
    assert before == after and before_files == after_files, 'Schema change rewrote data'
    assert nulls[0] > 0 and nulls[1] == 0, 'Old rows must have NULL quality_note'
    commands = statements(sql('07_time_travel.sql'))
    t.query(commands[0]); t.query(commands[1])
    snap = t.one(commands[2])
    original = t.query('SELECT * FROM lakehouse.demo.snapshot_example ORDER BY orderkey')
    t.query(commands[3])
    changed = t.query('SELECT * FROM lakehouse.demo.snapshot_example ORDER BY orderkey')
    changed_snap = t.one(commands[2])
    historical = sorted(t.query(commands[4].replace(':snapshot_id', str(int(snap)))))
    t.query(commands[5].replace(':snapshot_id', str(int(snap))))
    restored = sorted(t.query(commands[6]))
    assert len(changed) == len(original) - 1 and changed_snap != snap
    assert historical == sorted(original) == restored, 'Time travel/rollback failed'
    history = t.query('SELECT * FROM lakehouse.demo."snapshot_example$history" ORDER BY made_current_at')
    save('iceberg_demo.json', {'status': 'passed', 'run_id': read('pipeline.json')['run_id'],
        'evolution': {'before_schema': before_schema, 'after_schema': after_schema,
                      'before_files': before_files, 'after_files': after_files,
                      'before': before, 'after': after, 'rows': nulls[0], 'nonnull_notes': nulls[1]},
        'snapshot': {'initial_id': snap, 'changed_id': changed_snap, 'rows_before': len(original),
                     'rows_changed': len(changed), 'rows_historical': len(historical),
                     'rows_restored': len(restored), 'history': history}, 'queries': t.audit})
    print('Schema evolution without data rewrite, time travel and rollback verified')

if __name__ == '__main__':
    demo()
