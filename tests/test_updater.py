import zipfile
from pathlib import Path
import pytest
from src.PostalScanner_Updater import safe_extract_zip, validate_staged_app, effective_stage_root


def test_zip_slip_blocked(tmp_path):
    z = tmp_path / 'bad.zip'
    with zipfile.ZipFile(z, 'w') as f:
        f.writestr('../evil.txt', 'x')
    with pytest.raises(RuntimeError):
        safe_extract_zip(z, tmp_path / 'out')


def test_validate_requires_complete_package(tmp_path):
    root = tmp_path / 'PostalScanner'
    root.mkdir()
    (root / 'PostalScanner.exe').write_bytes(b'x' * (101 * 1024))
    (root / '_internal').mkdir()
    (root / 'updater').mkdir()
    (root / 'updater' / 'PostalScanner_Updater.exe').write_bytes(b'x')
    (root / 'resources').mkdir()
    (root / 'resources' / 'original_template.xlsx').write_bytes(b'x')
    assert validate_staged_app(root).name == 'PostalScanner.exe'


def test_effective_stage_root(tmp_path):
    outer = tmp_path / 'stage'; outer.mkdir()
    inner = outer / 'PostalScanner'; inner.mkdir()
    assert effective_stage_root(outer) == inner
