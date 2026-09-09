import sys
import tempfile
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))

from PostalScanner_Updater import validate_staged_app, copy_preserved_data


def test_validate_staged_app_rejects_missing_exe():
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        (root / '_internal').mkdir()
        try:
            validate_staged_app(root)
        except RuntimeError as e:
            assert 'PostalScanner.exe' in str(e)
        else:
            raise AssertionError('missing exe must fail')


def test_preserved_data_copy():
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        old = root / 'old'; new = root / 'new'
        old.mkdir(); new.mkdir()
        (old / 'data').mkdir()
        (old / 'data' / 'marker.txt').write_text('ok', encoding='utf-8')
        copy_preserved_data(old, new)
        assert (new / 'data' / 'marker.txt').read_text(encoding='utf-8') == 'ok'
