from pathlib import Path
import ast


def _source():
    return Path('src/PostalScanner.py').read_text(encoding='utf-8')


def _fn(name):
    s = _source()
    tree = ast.parse(s)
    node = next(x for x in tree.body if isinstance(x, ast.FunctionDef) and x.name == name)
    return ast.get_source_segment(s, node) or ''


def test_226_version_privacy_and_print_contract():
    s = _source()
    assert 'APP_VERSION = "2.2.6"' in s
    assert 'PRIVACY_MODE = True' in s
    assert 'PRIVACY_MAX_EXTERNAL_RATIO_LEDGER = 0.58' in s
    assert '"store": False' in s
    assert "('PrintArea', '$A$1:$K$49')" in s
    assert "('FitToPagesWide', 1)" in s
    assert "('FitToPagesTall', 1)" in s
    assert 'cv2.imwrite(' not in s


def test_ledger_recognition_uses_raw_direct_roi_only():
    fn = _fn('recognize_ledger_openai')
    assert '_build_ledger_direct_roi(frame)' in fn
    assert 'ledger_recognition_v226_direct_roi' in fn
    assert 'max_side=2200' in fn
    assert 'rectify_document(' not in fn
    assert '_build_ledger_focus_image(' not in fn
    assert '_ledger_select_last_written_row(' not in fn
    assert '_ledger_remove_grid(' not in fn


def test_direct_roi_is_fixed_and_below_privacy_limit():
    fn = _fn('_build_ledger_direct_roi')
    for token in ('0.10', '0.90', '0.33', '0.92'):
        assert token in fn
    assert 'frame[' in fn
    assert '.copy()' in fn


def test_prompt_lets_vision_choose_last_handwritten_row():
    s = _source()
    assert '보이는 모든 행을 비교' in s
    assert '가장 아래쪽 행 하나를 고른다' in s
    assert "인쇄된 시/도/구/시/군/장" in s
    assert "손글씨로 '외'가 있으면" in s


def test_general_mail_and_management_still_exist():
    s = _source()
    assert 'def recognize_general_openai(' in s
    assert 'def open_management(self):' in s
    assert 'PERSISTENT_ROOT = get_persistent_root()' in s
    assert 'DATA_DIR = PERSISTENT_ROOT / "data"' in s
    assert 'OPENAI_SECURE_KEY_FILE = DATA_DIR / "openai_key.dat"' in s
