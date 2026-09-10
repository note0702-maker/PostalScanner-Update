from pathlib import Path
import ast


def source():
    return Path('src/PostalScanner.py').read_text(encoding='utf-8')


def fn(name):
    s = source()
    tree = ast.parse(s)
    node = next(x for x in tree.body if isinstance(x, ast.FunctionDef) and x.name == name)
    return ast.get_source_segment(s, node) or ''


def test_version_and_one_page_a4_contract():
    s = source()
    assert 'APP_VERSION = "2.2.5"' in s
    helper = fn('_apply_postal_excel_display')
    assert "('PrintArea', '$A$1:$K$49')" in helper
    assert "('Zoom', False)" in helper
    assert "('FitToPagesWide', 1)" in helper
    assert "('FitToPagesTall', 1)" in helper
    assert "('Orientation', 1)" in helper
    assert "('PaperSize', 9)" in helper
    assert 'sheet.ResetAllPageBreaks()' in helper


def test_existing_excel_text_display_is_preserved():
    helper = fn('_apply_postal_excel_display')
    assert 'address_range.HorizontalAlignment = -4131' in helper
    assert 'address_range.ShrinkToFit = True' in helper
    assert 'recipient_cell.HorizontalAlignment = -4108' in helper
    assert 'recipient_cell.ShrinkToFit = True' in helper


def test_recognition_privacy_and_management_still_present():
    s = source()
    for token in (
        'ledger_recognition_v224_context',
        'max_side=2000',
        'PRIVACY_MODE = True',
        'PRIVACY_MAX_EXTERNAL_RATIO_LEDGER = 0.58',
        '"store": False',
        'def open_management(self):',
        'PERSISTENT_ROOT = get_persistent_root()',
        'DATA_DIR = PERSISTENT_ROOT / "data"',
    ):
        assert token in s
    assert 'cv2.imwrite(' not in s


def test_no_destructive_data_migration():
    migration = fn('_copy_legacy_data_once')
    assert 'shutil.move(' not in migration
    assert '.unlink(' not in migration
    assert 'rmtree' not in migration
