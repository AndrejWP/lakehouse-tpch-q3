"""Capture reproducibility metadata without container environment or secrets."""
import json
import platform
import subprocess
from pathlib import Path


def capture():
    info = json.loads(subprocess.check_output(['docker', 'info', '--format', '{{json .}}'], text=True))
    result = {
        'host_os': platform.system(), 'host_architecture': platform.machine(),
        'host_python': platform.python_version(), 'docker_engine': info['ServerVersion'],
        'docker_architecture': info['Architecture'], 'docker_memory_bytes': info['MemTotal'],
        'docker_cpus': info['NCPU'], 'trino_heap': '3G', 'trino_query_memory': '1500MB', 'scale': 'sf1'}
    target = Path(__file__).resolve().parents[1] / 'evidence/environment.json'
    target.write_text(json.dumps(result, indent=2) + '\n')
    print('Environment metadata saved (no credentials)')


if __name__ == '__main__':
    capture()
