from pathlib import Path
import ast
import re

p = Path('src/PostalScanner.py')
s = p.read_text(encoding='utf-8')

# Version bump from the production-safe 2.2.1 base.
s, n = re.subn(r'APP_VERSION\s*=\s*"2\.2\.1"', 'APP_VERSION = "2.2.2"', s, count=1)
if n != 1:
    raise SystemExit('APP_VERSION 2.2.1 anchor not found')

# Privacy mode is mandatory for the public-sector work build.
if 'PRIVACY_MODE = True' not in s:
    raise SystemExit('PRIVACY_MODE=True not found')
s, n1 = re.subn(
    r'PRIVACY_MAX_EXTERNAL_RATIO_GENERAL\s*=\s*0\.90',
    'PRIVACY_MAX_EXTERNAL_RATIO_GENERAL = 0.62',
    s,
    count=1,
)
s, n2 = re.subn(
    r'PRIVACY_MAX_EXTERNAL_RATIO_LEDGER\s*=\s*0\.80',
    'PRIVACY_MAX_EXTERNAL_RATIO_LEDGER = 0.58',
    s,
    count=1,
)
if n1 != 1 or n2 != 1:
    raise SystemExit('privacy ratio anchors not found')


def replace_top_function(source: str, name: str, replacement: str) -> str:
    tree = ast.parse(source)
    node = next((x for x in tree.body if isinstance(x, ast.FunctionDef) and x.name == name), None)
    if node is None:
        raise SystemExit(f'function not found: {name}')
    lines = source.splitlines()
    lines[node.lineno - 1:node.end_lineno] = replacement.rstrip('\n').splitlines()
    return '\n'.join(lines) + '\n'


# General-mail privacy ROI: intentionally excludes the top band where sender / return
# address / logos are commonly present. Only a broad recipient zone is allowed out.
s = replace_top_function(s, 'get_general_roi', '''def get_general_roi(frame):
    """기관 개인정보 최소전송: 상단 발신/회신 영역을 제외한 수취인 중심 영역만 반환한다."""
    if frame is None or getattr(frame, "size", 0) == 0:
        return None
    h, w = frame.shape[:2]
    x1, x2 = int(w * 0.06), int(w * 0.94)
    y1, y2 = int(h * 0.24), int(h * 0.92)
    roi = frame[max(0, y1):min(h, y2), max(0, x1):min(w, x2)].copy()
    return roi if getattr(roi, "size", 0) else None
''')

# Fail closed: a bad crop must cancel the request instead of silently sending the full frame.
s = replace_top_function(s, 'recognize_general_openai', '''def recognize_general_openai(frame, config):
    if not config:
        raise RuntimeError("OpenAI API 설정이 없습니다.")

    image = get_general_roi(frame)
    if image is None or getattr(image, "size", 0) == 0:
        raise RuntimeError(
            "개인정보 보호모드: 수취인 최소전송 영역을 만들지 못해 외부 전송을 중단했습니다."
        )

    _privacy_assert_external_image(
        image,
        frame.shape,
        PRIVACY_MAX_EXTERNAL_RATIO_GENERAL,
        "general",
    )

    primary = config.get("model", OPENAI_DEFAULT_MODEL)
    output_text = _call_openai_vision(
        config,
        primary,
        OPENAI_GENERAL_PROMPT,
        image,
        "general_mail_recognition",
        GENERAL_SCHEMA,
        max_output_tokens=120,
        max_side=1280,
    )
    result = _parse_openai_general_json(output_text)
    result["source"] = f"OpenAI Vision ({primary})"

    fallback = str(config.get("fallback_model", "") or "").strip()
    if fallback and fallback != primary and _general_result_needs_retry(result):
        ops_stats_add(openai_fallbacks=1)
        output_text = _call_openai_vision(
            config,
            fallback,
            OPENAI_GENERAL_PROMPT,
            image,
            "general_mail_fallback",
            GENERAL_SCHEMA,
            max_output_tokens=120,
            max_side=1440,
        )
        result = _parse_openai_general_json(output_text)
        result["source"] = f"OpenAI Vision ({primary} → {fallback})"

    image = None
    return result
''')

# Ledger privacy ROI: only the lower work-entry band is allowed out. The document may be
# rectified locally first, but a crop failure can never fall back to the whole document.
s = replace_top_function(s, 'recognize_ledger_openai', '''def recognize_ledger_openai(frame, config):
    if not config:
        raise RuntimeError("OpenAI API 설정이 없습니다.")

    document = rectify_document(frame)
    if document is None or getattr(document, "size", 0) == 0:
        raise RuntimeError(
            "개인정보 보호모드: 인감대장 전송영역을 만들지 못해 외부 전송을 중단했습니다."
        )

    h, w = document.shape[:2]
    x1, x2 = int(w * 0.08), int(w * 0.92)
    y1, y2 = int(h * 0.38), int(h * 0.98)
    image = document[max(0, y1):min(h, y2), max(0, x1):min(w, x2)].copy()

    if image is None or getattr(image, "size", 0) == 0:
        raise RuntimeError(
            "개인정보 보호모드: 인감대장 최소전송 영역을 만들지 못해 외부 전송을 중단했습니다."
        )

    _privacy_assert_external_image(
        image,
        document.shape,
        PRIVACY_MAX_EXTERNAL_RATIO_LEDGER,
        "ledger",
    )

    primary = config.get("model", OPENAI_DEFAULT_MODEL)
    output_text = _call_openai_vision(
        config,
        primary,
        OPENAI_LEDGER_PROMPT,
        image,
        "ledger_recognition",
        LEDGER_SCHEMA,
        max_output_tokens=100,
        max_side=1500,
    )
    result = _parse_openai_ledger_json(output_text)
    result["source"] = f"OpenAI Vision ({primary})"

    fallback = str(config.get("fallback_model", "") or "").strip()
    if fallback and fallback != primary and _ledger_result_needs_retry(result):
        ops_stats_add(openai_fallbacks=1)
        output_text = _call_openai_vision(
            config,
            fallback,
            OPENAI_LEDGER_PROMPT,
            image,
            "ledger_fallback",
            LEDGER_SCHEMA,
            max_output_tokens=100,
            max_side=1600,
        )
        result = _parse_openai_ledger_json(output_text)
        result["source"] = f"OpenAI Vision ({primary} → {fallback})"

    image = None
    document = None
    return result
''')

# Make the privacy behavior visible to the operator during every external call.
s = s.replace(
    '"촬영 품질을 확인한 뒤 OpenAI Vision으로 주소와 수신인을 "\n                    "해석하고 있습니다."',
    '"개인정보 보호모드: 수취인 영역만 잘라 OpenAI로 전송하고 있습니다. "\n                    "촬영 원본은 저장하지 않습니다."',
    1,
)
s = s.replace(
    '"촬영 품질을 확인한 뒤 OpenAI Vision으로 인감대장 양식과 손글씨를 "\n                    "해석하고 있습니다."',
    '"개인정보 보호모드: 대장 하단 작성영역만 잘라 OpenAI로 전송하고 있습니다. "\n                    "촬영 원본은 저장하지 않습니다."',
    1,
)

# Contract checks in the patch itself.
if '"store": False' not in s:
    raise SystemExit('Responses API store=false missing')
if 'cv2.imwrite(' in s:
    raise SystemExit('image file write detected in application source')

tree = ast.parse(s)
for fn_name, forbidden in (
    ('recognize_general_openai', 'frame.copy()'),
    ('recognize_ledger_openai', 'document.copy()'),
):
    fn = next(x for x in tree.body if isinstance(x, ast.FunctionDef) and x.name == fn_name)
    seg = ast.get_source_segment(s, fn) or ''
    if forbidden in seg:
        raise SystemExit(f'privacy fail-open fallback remains: {fn_name}')

p.write_text(s, encoding='utf-8')
print('2.2.2 privacy-minimization patch applied')
