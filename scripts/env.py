"""Create private local configuration without printing credentials."""
import os
import secrets
from pathlib import Path
p = Path('.env')
if p.exists():
    print('.env exists; preserved')
else:
    values = {
        'POSTGRES_PASSWORD': secrets.token_hex(24),
        'MINIO_ROOT_USER': 'lakehouse_admin',
        'MINIO_ROOT_PASSWORD': secrets.token_hex(24),
        'LAKEKEEPER_ENCRYPTION_KEY': secrets.token_hex(32),
        'SUPERSET_SECRET_KEY': secrets.token_hex(48),
        'SUPERSET_ADMIN_USER': 'admin',
        'SUPERSET_ADMIN_PASSWORD': secrets.token_hex(24),
    }
    fd = os.open(p, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, 'w') as f:
        f.write(''.join(f'{k}={v}\n' for k, v in values.items()))
    print('Created .env (0600); credentials are not printed')
