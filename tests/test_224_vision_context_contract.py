from pathlib import Path
import ast


def _source():
    return Path('src/PostalScanner.py').read_text(encoding='utf-8')


def _fn(name):
    s = _source()
    tree = ast.parse(s)
    node = next(x for x in tree.body if isinstance(x, ast.FunctionDef) and x.name == name)
    return ast.get_source_segment(s, node) or ''


def test_224_version_and_privacy_contract():
    s = _source()
    assert 'APP_VERSION = "2.2.4"' in s
    assert 'PRIVACY_MODE = True' in s
    assert 'PRIVACY_MAX_EXTERNAL_RATIO_LEDGER = 0.58' in s
    assert '"store": False' in s
    assert 'cv2.imwrite(' not in s


def test_ledger_model_gets_multi_row_context_not_single_row_projection():
    fn = _fn('_build_ledger_focus_image')
    for token in ('0.08', '0.94', '0.32'):
        assert token in fn
    assert '_ledger_select_last_written_row(' not in fn
    assert '.copy()' in fn


def test_prompt_requires_visual_row_comparison_and_anchor_reasoning():
    s = _source()
    assert '모든 행을 먼저 비교' in s
    assert '가장 아래쪽 행 하나를 선택' in s
    assert "인쇄된 '시/도/구/시/군/장'" in s
    assert "손글씨로 '외'가 있으면" in s


def test_ledger_call_keeps_high_resolution_and_no_full_frame_fallback():
    fn = _fn('recognize_ledger_openai')
    assert 'max_side=2000' in fn
    assert 'ledger_recognition_v224_context' in fn
    assert 'document.copy()' not in fn
    assert 'frame.copy()' not in fn


def test_persistent_and_management_architecture_still_present():
    s = _source()
    required = [
        'PERSISTENT_ROOT = get_persistent_root()',
        'DATA_DIR = PERSISTENT_ROOT / "data"',
        'OPENAI_SECURE_KEY_FILE = DATA_DIR / "openai_key.dat"',
        'def open_management(self):',
        'def _apply_postal_excel_display(',
    ]
    for token in required:
        assert token in s
