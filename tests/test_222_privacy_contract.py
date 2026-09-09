from pathlib import Path
import ast


def _source():
    return Path('src/PostalScanner.py').read_text(encoding='utf-8')


def _fn_segment(name):
    s = _source()
    tree = ast.parse(s)
    fn = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == name)
    return ast.get_source_segment(s, fn) or ''


def test_privacy_version_and_limits():
    s = _source()
    assert 'APP_VERSION = "2.2.2"' in s
    assert 'PRIVACY_MODE = True' in s
    assert 'PRIVACY_MAX_EXTERNAL_RATIO_GENERAL = 0.62' in s
    assert 'PRIVACY_MAX_EXTERNAL_RATIO_LEDGER = 0.58' in s


def test_general_roi_is_minimized_and_fail_closed():
    roi = _fn_segment('get_general_roi')
    for token in ('0.06', '0.94', '0.24', '0.92'):
        assert token in roi

    fn = _fn_segment('recognize_general_openai')
    assert 'get_general_roi(frame)' in fn
    assert 'PRIVACY_MAX_EXTERNAL_RATIO_GENERAL' in fn
    assert 'frame.copy()' not in fn
    assert '외부 전송을 중단했습니다' in fn


def test_ledger_roi_is_minimized_and_fail_closed():
    fn = _fn_segment('recognize_ledger_openai')
    for token in ('0.08', '0.92', '0.38', '0.98'):
        assert token in fn
    assert 'PRIVACY_MAX_EXTERNAL_RATIO_LEDGER' in fn
    assert 'document.copy()' not in fn
    assert '외부 전송을 중단했습니다' in fn


def test_openai_request_is_nonstored_and_images_not_written_to_disk():
    s = _source()
    fn = _fn_segment('_call_openai_vision')
    assert '"store": False' in fn
    assert 'cv2.imwrite(' not in s


def test_operator_sees_privacy_mode_message():
    s = _source()
    assert '수취인 영역만 잘라 OpenAI로 전송' in s
    assert '대장 하단 작성영역만 잘라 OpenAI로 전송' in s
    assert '촬영 원본은 저장하지 않습니다' in s
