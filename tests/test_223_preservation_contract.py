from pathlib import Path
import ast


def source():
    return Path('src/PostalScanner.py').read_text(encoding='utf-8')


def test_version_and_persistent_data_contract():
    s = source()
    assert 'APP_VERSION = "2.2.3"' in s
    assert 'PERSISTENT_ROOT = get_persistent_root()' in s
    assert 'DATA_DIR = PERSISTENT_ROOT / "data"' in s
    assert 'ORIGINAL_DIR = DATA_DIR / "original"' in s
    assert 'OUTPUT_DIR = DATA_DIR / "output"' in s
    assert 'AUDIT_DIR = DATA_DIR / "audit"' in s
    assert 'OPENAI_SECURE_KEY_FILE = DATA_DIR / "openai_key.dat"' in s


def test_management_ui_is_present():
    s = source()
    tree = ast.parse(s)
    app = next(x for x in tree.body if isinstance(x, ast.ClassDef) and x.name == 'PostalScannerApp')
    app_src = ast.get_source_segment(s, app) or ''
    assert 'def open_management(self):' in app_src
    assert '마지막 입력 취소' in app_src
    assert 'Excel 파일 열기' in app_src
    assert '업무 종료 및 개인정보 폐기' in app_src


def test_ledger_accuracy_patch_is_privacy_safe():
    s = source()
    assert 'def _build_ledger_focus_image(' in s
    assert 'def _ledger_select_last_written_row(' in s
    assert 'PRIVACY_MAX_EXTERNAL_RATIO_LEDGER = 0.58' in s
    assert '"store": False' in s
    assert 'cv2.imwrite(' not in s
    tree = ast.parse(s)
    fn = next(x for x in tree.body if isinstance(x, ast.FunctionDef) and x.name == 'recognize_ledger_openai')
    seg = ast.get_source_segment(s, fn) or ''
    assert 'document.copy()' not in seg
    assert '_build_ledger_focus_image(document)' in seg


def test_excel_visual_format_only():
    s = source()
    assert 'def _apply_postal_excel_display(' in s
    assert 'address_range.HorizontalAlignment = -4131' in s
    assert 'address_range.ShrinkToFit = True' in s
    assert 'recipient_cell.HorizontalAlignment = -4108' in s
    assert 'recipient_cell.ShrinkToFit = True' in s
    assert '.Merge(' not in s
    assert '.UnMerge(' not in s
