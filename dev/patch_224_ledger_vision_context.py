from pathlib import Path
import ast
import hashlib
import re

p = Path('src/PostalScanner.py')
s = p.read_text(encoding='utf-8')


def parse_top(source):
    return ast.parse(source)


def node_segment(source, node):
    return ast.get_source_segment(source, node) or ''


def top_function_node(source, name):
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


def replace_top_function(source, name, replacement):
    return replace_node_lines(source, top_function_node(source, name), replacement)


# ---------------------------------------------------------------------------
# 2.2.4 goal
# Let the vision model reason over several complete ledger rows, like a human
# reviewing the form, instead of making local OpenCV decide the exact final row.
# UI / management / settings / persistent data / updater remain untouched.
# ---------------------------------------------------------------------------
required = [
    'APP_VERSION = "2.2.3"',
    'PERSISTENT_ROOT = get_persistent_root()',
    'DATA_DIR = PERSISTENT_ROOT / "data"',
    'ORIGINAL_DIR = DATA_DIR / "original"',
    'OUTPUT_DIR = DATA_DIR / "output"',
    'AUDIT_DIR = DATA_DIR / "audit"',
    'OPENAI_SECURE_KEY_FILE = DATA_DIR / "openai_key.dat"',
    'PRIVACY_MODE = True',
    'PRIVACY_MAX_EXTERNAL_RATIO_GENERAL = 0.62',
    'PRIVACY_MAX_EXTERNAL_RATIO_LEDGER = 0.58',
    '"store": False',
    'def open_management(self):',
    'def _apply_postal_excel_display(',
]
missing = [x for x in required if x not in s]
if missing:
    raise SystemExit('2.2.3 preserved architecture mismatch: ' + repr(missing))

ui_before = node_segment(s, class_node(s, 'PostalScannerApp'))
protected_names = [
    'get_persistent_root',
    '_copy_legacy_data_once',
    'save_secure_openai_api_key',
    'load_secure_openai_api_key',
    'load_openai_config',
    'load_update_config',
    'write_excel',
]
protected_before = {name: node_segment(s, top_function_node(s, name)) for name in protected_names}

# Version bump only.
s, count = re.subn(r'APP_VERSION\s*=\s*"2\.2\.3"', 'APP_VERSION = "2.2.4"', s, count=1)
if count != 1:
    raise SystemExit('APP_VERSION 2.2.3 anchor not found')

# Replace the prompt assignment using AST line coordinates to avoid regex damage.
tree = parse_top(s)
prompt_node = None
for x in tree.body:
    if isinstance(x, ast.Assign):
        if any(isinstance(t, ast.Name) and t.id == 'OPENAI_LEDGER_PROMPT' for t in x.targets):
            prompt_node = x
            break
if prompt_node is None:
    raise SystemExit('OPENAI_LEDGER_PROMPT assignment not found')

prompt = '''OPENAI_LEDGER_PROMPT = r"""
너는 고정 양식 '인감대장송부'를 사람처럼 전체 문맥으로 판독한다.
이미지에는 개인정보 최소화를 위해 문서 전체가 아니라 업무 표의 하단 여러 행만 보인다.

핵심 절차:
1. 이미지에 보이는 모든 행을 먼저 비교한다.
2. 수신기관명 영역 또는 성명 영역에 실제 손글씨가 있는 행들 중 가장 아래쪽 행 하나를 선택한다.
3. 한 행의 손글씨는 같은 높이에 가지런하지 않을 수 있다. 글씨가 인쇄된 '시/도/구/시/군/장'의 위나 아래에 있어도 같은 행의 내용으로 해석한다.
4. 취소선, 덧칠, 검게 지운 흔적은 현재 값으로 읽지 않는다. 그 행에서 최종적으로 남아 있는 손글씨를 우선한다.
5. 인쇄된 시/도/구/시/군/장 글자는 값 자체가 아니라 위치를 알려주는 고정 앵커다.

수신기관명 복원 규칙:
- 손글씨와 인쇄 앵커를 결합해 공식 기관명으로 만든다.
- 예: '경북' + 인쇄 '도' -> '경상북도'
- 예: '포항' + 인쇄 '시', '남' + 인쇄 '구', '대이동' + 인쇄 '장' -> '포항시 남구 대이동장'
- 예: '서울' + '특별', '송파' + 인쇄 '구', '거여2동' + 인쇄 '장' -> '서울특별시 송파구 거여2동장'
- 보이는 정보만 사용하고, 글씨가 불명확하면 억지로 추측하지 않는다.

성명 규칙:
- 가장 오른쪽 성명/등기번호 쪽 칸의 손글씨를 그대로 읽는다.
- 이름 뒤에 손글씨로 '외'가 있으면 '외'까지 포함한다.
- 귀하/님 같은 호칭은 임의로 붙이지 않는다.

빈 행, 인쇄된 안내문, 표 제목, 행번호, 우편번호, QR/바코드, 하단 문구는 결과에서 제외한다.
반드시 지정된 JSON 형식만 반환한다.
"""'''
s = replace_node_lines(s, prompt_node, prompt)

# Human-like context crop: several complete lower ledger rows are kept together.
# This deliberately removes the brittle "OpenCV chooses one exact row" decision.
new_focus = '''def _build_ledger_focus_image(document):
    """Return a privacy-bounded multi-row context image for vision reasoning."""
    if document is None or getattr(document, "size", 0) == 0:
        raise RuntimeError(
            "개인정보 보호모드: 인감대장 문서영역을 만들지 못했습니다."
        )

    h, w = document.shape[:2]

    # Keep several complete rows so the model itself can compare rows and choose
    # the bottom-most handwritten one. The crop is ~53.3% of source pixel area:
    # 86% width x 62% height, below the existing 58% privacy guard.
    x1 = int(w * 0.08)
    x2 = int(w * 0.94)
    y1 = int(h * 0.32)
    y2 = int(h * 0.94)

    image = document[
        max(0, y1):min(h, y2),
        max(0, x1):min(w, x2),
    ].copy()
    if image.size == 0:
        raise RuntimeError(
            "개인정보 보호모드: 인감대장 문맥영역을 만들지 못해 외부 전송을 중단했습니다."
        )
    return image
'''
s = replace_top_function(s, '_build_ledger_focus_image', new_focus)

new_recognize = '''def recognize_ledger_openai(frame, config):
    if not config:
        raise RuntimeError("OpenAI API 설정이 없습니다.")

    document = rectify_document(frame)
    if document is None or getattr(document, "size", 0) == 0:
        raise RuntimeError(
            "개인정보 보호모드: 인감대장 전송영역을 만들지 못해 외부 전송을 중단했습니다."
        )

    image = _build_ledger_focus_image(document)
    _privacy_assert_external_image(
        image,
        document.shape,
        PRIVACY_MAX_EXTERNAL_RATIO_LEDGER,
        "ledger",
    )

    # Use the configured stronger model for handwriting/context reasoning when
    # available. General-mail recognition remains completely unchanged.
    primary = str(config.get("model", OPENAI_DEFAULT_MODEL) or OPENAI_DEFAULT_MODEL).strip()
    stronger = str(config.get("fallback_model", "") or "").strip()
    ledger_model = stronger if stronger and stronger != primary else primary

    output_text = _call_openai_vision(
        config,
        ledger_model,
        OPENAI_LEDGER_PROMPT,
        image,
        "ledger_recognition_v224_context",
        LEDGER_SCHEMA,
        max_output_tokens=120,
        max_side=2000,
    )
    result = _parse_openai_ledger_json(output_text)
    result["institution"] = normalize_ledger_address(result.get("institution", ""))
    result["source"] = f"OpenAI Vision context ({ledger_model})"

    # Explicitly release image references after the request.
    image = None
    document = None
    return result
'''
s = replace_top_function(s, 'recognize_ledger_openai', new_recognize)

# ---------------------------------------------------------------------------
# Preservation verification
# ---------------------------------------------------------------------------
ui_after = node_segment(s, class_node(s, 'PostalScannerApp'))
if hashlib.sha256(ui_before.encode('utf-8')).hexdigest() != hashlib.sha256(ui_after.encode('utf-8')).hexdigest():
    raise SystemExit('UI/management/settings class changed unexpectedly')

for name, before in protected_before.items():
    after = node_segment(s, top_function_node(s, name))
    if before != after:
        raise SystemExit(f'protected function changed unexpectedly: {name}')

if 'shutil.move(' in s:
    raise SystemExit('destructive migration call detected')
if 'cv2.imwrite(' in s:
    raise SystemExit('captured image disk write detected')

ledger_seg = node_segment(s, top_function_node(s, 'recognize_ledger_openai'))
if 'document.copy()' in ledger_seg or 'frame.copy()' in ledger_seg:
    raise SystemExit('full-frame ledger fallback detected')

p.write_text(s, encoding='utf-8')
print('2.2.4 vision-context ledger patch applied; UI/settings/data/excel preserved')
