"""Build a submission ZIP from Git publication candidates without staging or committing."""
import hashlib
import zipfile
from pathlib import Path
from audit import forbidden, publication_files, security
from common import ROOT


def package():
    files = publication_files()
    security(files)
    output = ROOT / 'dist/lakehouse-tpch-q3.zip'
    output.parent.mkdir(exist_ok=True)
    with zipfile.ZipFile(output, 'w', compression=zipfile.ZIP_DEFLATED) as z:
        for name in files:
            z.write(ROOT / name, 'lakehouse-tpch-q3/' + name)
    with zipfile.ZipFile(output) as z:
        assert z.testzip() is None, 'Invalid archive'
        assert not any(forbidden(n) for n in z.namelist())
        for name in files:
            assert z.read('lakehouse-tpch-q3/' + name) == (ROOT / name).read_bytes()
    print(f'Created {output.name}: {len(files)} files, SHA256 {hashlib.sha256(output.read_bytes()).hexdigest()}')


if __name__ == '__main__':
    package()
