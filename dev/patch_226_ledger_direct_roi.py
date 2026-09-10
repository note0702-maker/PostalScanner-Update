from pathlib import Path
import ast
import hashlib
import re

p = Path('src/PostalScanner.py')
s = p.read_text(encoding='utf-8')


def parse_top(source):
    return ast.parse(source)


def segment(source, node):
    return ast.get_source_segment(source, node) or ''


def fn_node(source, name):
    tree = parse_top(source)
    node = next((x for x in tree.body if isinstance(x, ast.FunctionDef) and x.name == name), None)
    if node is None:
        raise SystemExit(f'function not found: {name}')
    return node


def class_node(source, name):
    tree = parse_top(source)
    node = next((x for x in tree.body if isinstance(x, ast.ClassDef) and x.name == name), None)
    if node is None:
        raise SystemExit(f'class not found: {name}')
    return node


def replace_node_lines(source, node, replacement):
    lines = source.splitlines()
    lines[node.lineno - 1:node.end_lineno] = replacement.rstrip('\n').splitlines()
    return '\n'.join(lines) + '\n'


def replace_fn(source, name, replacement):
    return replace_node_lines(source, fn_node(source, name), replacement)


required = [
    'APP_VERSION = "2.2.5"',
    'PERSISTENT_ROOT = get_persistent_root()',
    'DATA_DIR = PERSISTENT_ROOT / "data"',
    'OPENAI_SECURE_KEY_FILE = DATA_DIR / "openai_key.dat"',
    'PRIVACY_MODE = True',
    'PRIVACY_MAX_EXTERNAL_RATIO_LEDGER = 0.58',
    '"store": False',
    'ledger_recognition_v224_context',
    'def open_management(self):',
    "('PrintArea', '$A$1:$K$49')",
    "('FitToPagesWide', 1)",
    "('FitToPagesTall', 1)",
]
missing = [x for x in required if x not in s]
if missing:
    raise SystemExit('2.2.5 preserved source mismatch: ' + repr(missing))

# GENERAL MAIL / UI / SETTINGS / DATA / EXCEL / UPDATER MUST NOT CHANGE.
ui_before = segment(s, class_node(s, 'PostalScannerApp'))
protected_names = [
    'get_persistent_root',
    '_copy_legacy_data_once',
    'save_secure_openai_api_key',
    'load_secure_openai_api_key',
    'load_openai_config',
    'load_update_config',
    'recognize_general_openai',
    '_apply_postal_excel_display',
    'write_excel',
]
protected_before = {name: segment(s, fn_node(s, name)) for name in protected_names}

s, count = re.subn(r'APP_VERSION\s*=\s*"2\.2\.5"', 'APP_VERSION = "2.2.6"', s, count=1)
if count != 1:
    raise SystemExit('APP_VERSION 2.2.5 anchor not found')

# Replace only the ledger prompt. The model receives a fixed raw-camera ROI with
# several visible rows and decides the bottom-most handwritten row itself.
tree = parse_top(s)
prompt_node = None
for x in tree.body:
    if isinstance(x, ast.Assign) and any(
        isinstance(t, ast.Name) and t.id == 'OPENAI_LEDGER_PROMPT' for t in x.targets
    ):
        prompt_node = x
        break
if prompt_node is None:
    raise SystemExit('OPENAI_LEDGER_PROMPT assignment not found')

prompt = r'''OPENAI_LEDGER_PROMPT = r"""
너는 고정 양식 '인감대장송부'의 하단 여러 행을 사람처럼 직접 보고 판독한다.
이미지는 카메라 원본에서 필요한 표 영역만 고정 사각형으로 잘라낸 것이며,
표선 제거, 마지막 행 자동탐지, 문서 원근보정 같은 전처리는 하지 않았다.

판독 절차:
1. 보이는 모든 행을 비교한다.
2. 수신기관명 또는 성명 칸에 실제 손글씨가 있는 행 중 가장 아래쪽 행 하나를 고른다.
3. 손글씨가 같은 높이에 가지런하지 않아도 같은 행 안의 내용으로 판단한다.
4. 인쇄된 시/도/구/시/군/장 글자는 값 자체가 아니라 위치 앵커로 사용한다.
5. 손글씨와 인쇄 앵커를 결합해 공식 행정기관명으로 복원한다.
   예: 경북 + 인쇄 '도' -> 경상북도
   예: 영덕 + 인쇄 '군', 영덕읍 + 인쇄 '장' -> 영덕군 영덕읍장
   예: 송파 + 인쇄 '구', 거여2동 + 인쇄 '장' -> 송파구 거여2동장
6. 가장 오른쪽 성명/등기번호 쪽 손글씨 이름을 그대로 읽는다.
7. 이름 뒤에 손글씨로 '외'가 있으면 '외'까지 포함한다.
8. 취소선, 덧칠, 검게 지운 흔적은 현재 값으로 읽지 않는다.
9. 보이지 않는 글자는 추측하지 않는다.

제목, 행번호, 빈 행, 인쇄된 안내문, 우편번호, QR/바코드는 결과에서 제외한다.
반드시 지정된 JSON 형식만 반환한다.
"""'''
s = replace_node_lines(s, prompt_node, prompt)

# Add a simple raw-frame ROI helper immediately before the ledger recognizer.
# 80% width x 59% height = 47.2% of the raw frame, safely below the existing
# 58% external-image area guard. No line removal, projection, or row selection.
helper = r'''def _build_ledger_direct_roi(frame):
    if frame is None or getattr(frame, "size", 0) == 0:
        raise RuntimeError("인감대장 카메라 프레임이 없습니다.")

    h, w = frame.shape[:2]
    x1 = int(w * 0.10)
    x2 = int(w * 0.90)
    y1 = int(h * 0.33)
    y2 = int(h * 0.92)

    roi = frame[
        max(0, y1):min(h, y2),
        max(0, x1):min(w, x2),
    ].copy()
    if roi.size == 0:
        raise RuntimeError("인감대장 고정 인식영역을 만들지 못했습니다.")
    return roi
'''
ledger_anchor = 'def recognize_ledger_openai(frame, config):'
if ledger_anchor not in s:
    raise SystemExit('recognize_ledger_openai anchor not found')
s = s.replace(ledger_anchor, helper.rstrip() + '\n\n' + ledger_anchor, 1)

new_ledger = r'''def recognize_ledger_openai(frame, config):
    if not config:
        raise RuntimeError("OpenAI API 설정이 없습니다.")

    # 2.2.6 ledger-only path: raw camera -> fixed ROI -> Vision.
    # Do NOT rectify the document, remove grid lines, or auto-select a row.
    image = _build_ledger_direct_roi(frame)
    _privacy_assert_external_image(
        image,
        frame.shape,
        PRIVACY_MAX_EXTERNAL_RATIO_LEDGER,
        "ledger",
    )

    primary = str(config.get("model", OPENAI_DEFAULT_MODEL) or OPENAI_DEFAULT_MODEL).strip()
    stronger = str(config.get("fallback_model", "") or "").strip()
    ledger_model = stronger if stronger and stronger != primary else primary

    output_text = _call_openai_vision(
        config,
        ledger_model,
        OPENAI_LEDGER_PROMPT,
        image,
        "ledger_recognition_v226_direct_roi",
        LEDGER_SCHEMA,
        max_output_tokens=120,
        max_side=2200,
    )
    result = _parse_openai_ledger_json(output_text)
    result["institution"] = normalize_ledger_address(result.get("institution", ""))
    result["source"] = f"OpenAI Vision direct ROI ({ledger_model})"

    image = None
    return result
'''
s = replace_fn(s, 'recognize_ledger_openai', new_ledger)

# Preservation verification after ledger-only changes.
ui_after = segment(s, class_node(s, 'PostalScannerApp'))
if hashlib.sha256(ui_before.encode('utf-8')).hexdigest() != hashlib.sha256(ui_after.encode('utf-8')).hexdigest():
    raise SystemExit('UI/settings changed unexpectedly')

for name, before in protected_before.items():
    after = segment(s, fn_node(s, name))
    if before != after:
        raise SystemExit(f'protected non-ledger function changed unexpectedly: {name}')

ledger_after = segment(s, fn_node(s, 'recognize_ledger_openai'))
for forbidden in (
    'rectify_document(',
    '_build_ledger_focus_image(',
    '_ledger_select_last_written_row(',
    '_ledger_remove_grid(',
):
    if forbidden in ledger_after:
        raise SystemExit('old ledger preprocessing still active: ' + forbidden)

if '_build_ledger_direct_roi(frame)' not in ledger_after:
    raise SystemExit('direct ledger ROI is not active')
if 'ledger_recognition_v226_direct_roi' not in ledger_after:
    raise SystemExit('2.2.6 ledger call tag missing')
if 'cv2.imwrite(' in s:
    raise SystemExit('captured image disk write detected')
if 'shutil.move(' in s:
    raise SystemExit('destructive migration call detected')

p.write_text(s, encoding='utf-8')
print('2.2.6 ledger direct ROI patch applied; general mail/UI/print/settings/data/updater preserved')
