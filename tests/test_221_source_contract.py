from pathlib import Path
import ast


def _source():
    return Path('src/PostalScanner.py').read_text(encoding='utf-8')


def test_version_and_persistent_data_root():
    s = _source()
    assert 'APP_VERSION = "2.2.1"' in s
    assert 'LOCALAPPDATA' in s
    assert 'PERSISTENT_ROOT' in s
    assert 'DATA_DIR = PERSISTENT_ROOT / "data"' in s


def test_legacy_migration_is_copy_only():
    s = _source()
    tree = ast.parse(s)
    fn = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == 'migrate_legacy_data_layout')
    segment = ast.get_source_segment(s, fn) or ''
    assert 'shutil.copytree' in segment
    assert 'shutil.copy2' in segment
    assert 'shutil.move' not in segment
    assert '.unlink(' not in segment
    assert 'rmtree' not in segment


def test_business_data_paths_under_data_dir():
    s = _source()
    for token in (
        'ORIGINAL_DIR = DATA_DIR / "original"',
        'OUTPUT_DIR = DATA_DIR / "output"',
        'AUDIT_DIR = DATA_DIR / "audit"',
        'OPENAI_SECURE_KEY_FILE = DATA_DIR / "openai_key.dat"',
    ):
        assert token in s
