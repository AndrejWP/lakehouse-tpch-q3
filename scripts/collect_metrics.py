from common import Trino, read, save

def collect():
    t = Trino()
    tables = {}
    for table in ['bronze.customer', 'bronze.orders', 'bronze.lineitem', 'silver.shipping_order_lines', 'gold.shipping_priority']:
        full = 'lakehouse.' + table
        ns, name = full.rsplit('.', 1)
        tables[table] = {
            'rows': t.one(f'SELECT count(*) FROM {full}'),
            'columns': t.query(f'SHOW COLUMNS FROM {full}'),
            'definition': t.one(f'SHOW CREATE TABLE {full}'),
            'properties': t.query(f'SELECT * FROM {ns}."{name}$properties"'),
            'partitioning': 'unpartitioned', **t.metrics(full)}
    save('metrics.json', {'run_id': read('pipeline.json')['run_id'], 'scale': 'sf1',
                          'trino_version': t.one('SELECT version()'), 'tables': tables, 'queries': t.audit})
    print('Active Iceberg data-file metrics collected')

if __name__ == '__main__':
    collect()
