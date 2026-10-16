import json
import sys
from pathlib import Path
text = Path(sys.argv[1]).read_text()
# Compose v2 uses NDJSON; newer versions can return a JSON array.
rows = json.loads(text) if text.lstrip().startswith('[') else [json.loads(r) for r in text.splitlines() if r.strip()]
services = {r['Service']: r for r in rows}
for name in ['postgres', 'minio', 'lakekeeper', 'trino', 'superset']:
    assert name in services, f'Service missing: {name}'
    row = services[name]
    assert row['State'] == 'running' and row['Health'] == 'healthy', f'{name}: {row["State"]}/{row["Health"]}'
# Save only reproducibility fields; omit host paths, labels and container internals.
Path(sys.argv[1]).write_text(json.dumps([{k: row.get(k) for k in ['Service', 'Image', 'State', 'Health', 'Status']} for row in rows], indent=2) + '\n')
print('Five persistent services healthy')
