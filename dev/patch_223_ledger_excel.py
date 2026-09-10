from pathlib import Path
import ast
import hashlib
import re

p = Path('src/PostalScanner.py')
s = p.read_text(encoding='utf-8')


def parse_top(source):
    return ast.parse(source)


def top_function_segment(source, name):
    tree = parse_top(source)
    node = next((x for x in tree.body if isinstance(x, ast.FunctionDef) and x.name == name), None)
    if node is None:
        raise SystemExit(f'function not found: {name}')
    return ast.get_source_segment(source, node) or ''


def class_segment(source, name):
    tree = parse_top(source)
    node = next((x for x in tree.body if isinstance(x, ast.ClassDef) and x.name == name), None)
    if node is None:
        raise SystemExit(f'class not found: {name}')
    return ast.get_source_segment(source, node) or ''


def replace_top_function(source, name, replacement):
    tree = parse_top(source)
    node = next((x for x in tree.body if isinstance(x, ast.FunctionDef) and x.name == name), None)
    if node is None:
        raise SystemExit(f'function not found: {name}')
    lines = source.splitlines()
    lines[node.lineno - 1:node.end_lineno] = replacement.rstrip('\n').splitlines()
    return '\n'.join(lines) + '\n'


# ------------------------------------------------------------------
# PRESERVATION GUARDS
# 2.2.3 must be a surgical behavior patch. UI / management / settings /
# persistent data / updater configuration are not allowed to change here.
# ------------------------------------------------------------------
required_architecture = [
    'APP_VERSION = "2.2.2"',
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
]
missing = [x for x in required_architecture if x not in s]
if missing:
    raise SystemExit('2.2.2 production architecture mismatch: ' + repr(missing))

ui_before = class_segment(s, 'PostalScannerApp')
protected_functions = [
    'get_persistent_root',
    '_copy_legacy_data_once',
    'save_secure_openai_api_key',
    'load_secure_openai_api_key',
    'load_openai_config',
    'load_update_config',
]
protected_before = {name: top_function_segment(s, name) for name in protected_functions}

# Version bump only. Do not rebuild from an old 2.1.x source.
s, n = re.subn(r'APP_VERSION\s*=\s*"2\.2\.2"', 'APP_VERSION = "2.2.3"', s, count=1)
if n != 1:
    raise SystemExit('APP_VERSION 2.2.2 anchor not found')

# ------------------------------------------------------------------
# LEDGER ACCURACY
# Keep general-mail recognition untouched. For the fixed ledger form, detect
# the bottom-most written grid row locally, then send a compact focus canvas:
# row context + enlarged institution zone + enlarged name zone.
# No full-frame fallback is allowed.
# ------------------------------------------------------------------
new_prompt = r'''OPENAI_LEDGER_PROMPT = r"""
고정 양식 '인감대장송부'의 가장 아래쪽 실제 작성행 한 줄만 판독하라.
전송 이미지는 개인정보 최소전송을 위해 한 행을 중심으로 재구성된 보조 이미지다.
위쪽 패널은 마지막 작성행 전체, 아래쪽 왼쪽은 수신기관명 영역 확대,
아래쪽 오른쪽은 등기번호 열에 손글씨로 적힌 이름 영역 확대다.

수신기관명은 고정 양식의 인쇄된 시/도/구/시/군/장 위치와 손글씨를 결합해
공식 행정기관명으로 복원한다.
예: 경북+도=경상북도, 포항+시=포항시, 남+구=남구, 대이동+장=대이동장.
도 약칭은 공식 명칭으로 정규화한다.
등기번호 열에 적힌 손글씨 한글 이름은 이 업무에서 수신인 이름이다.
이름 끝에 귀하/님을 붙이지 않는다.
제목, 표제, 행번호, 빈 행, 인쇄된 양식 글자 자체는 결과에 넣지 않는다.
보이지 않는 글자는 추측하지 말고 불확실하면 빈 문자열로 반환한다.
설명 없이 지정된 JSON 형식으로만 반환한다.
"""'''

prompt_pattern = re.compile(r'OPENAI_LEDGER_PROMPT\s*=\s*r""".*?"""', re.S)
s, count = prompt_pattern.subn(new_prompt, s, count=1)
if count != 1:
    raise SystemExit('OPENAI_LEDGER_PROMPT anchor not found')

helpers = r'''
def _ledger_remove_grid(gray):
    """Remove most printed grid lines locally while retaining handwriting strokes."""
    _, binary = cv2.threshold(
        gray,
        0,
        255,
        cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU,
    )
    h, w = gray.shape[:2]
    hk = cv2.getStructuringElement(cv2.MORPH_RECT, (max(28, w // 7), 1))
    vk = cv2.getStructuringElement(cv2.MORPH_RECT, (1, max(20, h // 5)))
    horizontal = cv2.morphologyEx(binary, cv2.MORPH_OPEN, hk)
    vertical = cv2.morphologyEx(binary, cv2.MORPH_OPEN, vk)
    grid = cv2.max(horizontal, vertical)
    text = cv2.subtract(binary, grid)
    text = cv2.morphologyEx(
        text,
        cv2.MORPH_CLOSE,
        cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3)),
        iterations=1,
    )
    return binary, horizontal, text


def _ledger_horizontal_line_centers(horizontal):
    if horizontal is None or getattr(horizontal, 'size', 0) == 0:
        return []
    h, w = horizontal.shape[:2]
    row_pixels = (horizontal > 0).sum(axis=1)
    threshold = max(12, int(w * 0.40))
    runs = []
    start = None
    for y, count in enumerate(row_pixels):
        if int(count) >= threshold and start is None:
            start = y
        elif int(count) < threshold and start is not None:
            runs.append((start, y - 1))
            start = None
    if start is not None:
        runs.append((start, h - 1))
    return [int(round((a + b) / 2.0)) for a, b in runs]


def _ledger_select_last_written_row(focus):
    """Use the fixed table grid and extra ink to select the bottom-most written row."""
    gray = cv2.cvtColor(focus, cv2.COLOR_BGR2GRAY)
    _binary, horizontal, text = _ledger_remove_grid(gray)
    centers = _ledger_horizontal_line_centers(horizontal)

    candidates = []
    if len(centers) >= 3:
        fw = focus.shape[1]
        x1 = int(fw * 0.05)
        x2 = int(fw * 0.96)
        for top, bottom in zip(centers[:-1], centers[1:]):
            height = bottom - top
            if height < 20 or height > max(220, int(focus.shape[0] * 0.28)):
                continue
            y1 = min(bottom - 2, top + max(4, int(height * 0.10)))
            y2 = max(y1 + 1, bottom - max(4, int(height * 0.10)))
            roi = text[y1:y2, x1:x2]
            if roi.size == 0:
                continue
            density = float((roi > 0).sum()) / float(roi.size)
            candidates.append((top, bottom, density))

    if candidates:
        densities = sorted(x[2] for x in candidates)
        baseline = densities[len(densities) // 2]
        peak = max(densities)
        threshold = max(0.0030, baseline * 1.30, peak * 0.30)
        written = [item for item in candidates if item[2] >= threshold]
        if written:
            top, bottom, _ = written[-1]
            margin = max(8, int((bottom - top) * 0.12))
            return max(0, top - margin), min(focus.shape[0], bottom + margin)

    # Conservative fallback: use connected ink bands, never the full document.
    projection = (text > 0).sum(axis=1)
    active_threshold = max(4, int(focus.shape[1] * 0.008))
    runs = []
    start = None
    for y, count in enumerate(projection):
        if int(count) >= active_threshold and start is None:
            start = y
        elif int(count) < active_threshold and start is not None:
            if y - start >= 10:
                runs.append((start, y - 1))
            start = None
    if start is not None and focus.shape[0] - start >= 10:
        runs.append((start, focus.shape[0] - 1))
    if not runs:
        return None
    top, bottom = runs[-1]
    margin = max(14, int((bottom - top + 1) * 0.65))
    return max(0, top - margin), min(focus.shape[0], bottom + margin)


def _fit_panel(image, target_w, target_h):
    h, w = image.shape[:2]
    if h <= 0 or w <= 0:
        raise RuntimeError('인감대장 확대영역이 비어 있습니다.')
    scale = min(target_w / float(w), target_h / float(h))
    scale = max(scale, 0.01)
    resized = cv2.resize(
        image,
        (max(1, int(w * scale)), max(1, int(h * scale))),
        interpolation=cv2.INTER_CUBIC if scale > 1.0 else cv2.INTER_AREA,
    )
    return resized


def _build_ledger_focus_image(document):
    """Build a compact privacy-safe canvas from only the final working row."""
    if document is None or getattr(document, 'size', 0) == 0:
        raise RuntimeError('개인정보 보호모드: 인감대장 문서영역을 만들지 못했습니다.')

    h, w = document.shape[:2]
    focus = document[
        int(h * 0.30):int(h * 0.97),
        int(w * 0.06):int(w * 0.94),
    ].copy()
    if focus.size == 0:
        raise RuntimeError('개인정보 보호모드: 인감대장 작업영역을 만들지 못했습니다.')

    band = _ledger_select_last_written_row(focus)
    if band is None:
        raise RuntimeError('개인정보 보호모드: 인감대장의 마지막 작성행을 찾지 못했습니다.')
    y1, y2 = band
    row = focus[y1:y2, :].copy()
    if row.size == 0:
        raise RuntimeError('개인정보 보호모드: 인감대장 마지막 작성행을 만들지 못했습니다.')

    rh, rw = row.shape[:2]
    # Fixed-form broad zones. They intentionally overlap slightly so handwriting
    # near a vertical border is not clipped.
    institution = row[:, int(rw * 0.05):int(rw * 0.78)].copy()
    name = row[:, int(rw * 0.70):int(rw * 0.98)].copy()

    target_w = max(700, min(1500, int(w * 0.86)))
    row_h = max(120, min(360, int(h * 0.17)))
    detail_h = max(120, min(360, int(h * 0.16)))
    gap = 12

    row_panel = _fit_panel(row, target_w, row_h)
    inst_w = int((target_w - gap) * 0.70)
    name_w = max(1, target_w - gap - inst_w)
    inst_panel = _fit_panel(institution, inst_w, detail_h)
    name_panel = _fit_panel(name, name_w, detail_h)

    canvas_h = row_h + detail_h + gap * 3
    canvas = np.full((canvas_h, target_w, 3), 255, dtype=np.uint8)

    rx = (target_w - row_panel.shape[1]) // 2
    ry = gap + (row_h - row_panel.shape[0]) // 2
    canvas[ry:ry + row_panel.shape[0], rx:rx + row_panel.shape[1]] = row_panel

    lower_y = row_h + gap * 2
    ix = (inst_w - inst_panel.shape[1]) // 2
    iy = lower_y + (detail_h - inst_panel.shape[0]) // 2
    canvas[iy:iy + inst_panel.shape[0], ix:ix + inst_panel.shape[1]] = inst_panel

    nx0 = inst_w + gap
    nx = nx0 + (name_w - name_panel.shape[1]) // 2
    ny = lower_y + (detail_h - name_panel.shape[0]) // 2
    canvas[ny:ny + name_panel.shape[0], nx:nx + name_panel.shape[1]] = name_panel

    # The external-image guard checks encoded canvas area against the rectified
    # source area. Downscale only if needed; never expand to a full-frame image.
    max_area = max(1.0, float(h * w) * 0.54)
    area = float(canvas.shape[0] * canvas.shape[1])
    if area > max_area:
        scale = (max_area / area) ** 0.5
        canvas = cv2.resize(
            canvas,
            (max(1, int(canvas.shape[1] * scale)), max(1, int(canvas.shape[0] * scale))),
            interpolation=cv2.INTER_AREA,
        )
    return canvas
'''

# Insert helpers immediately before recognize_ledger_openai so no UI code moves.
ledger_anchor = 'def recognize_ledger_openai(frame, config):'
if ledger_anchor not in s:
    raise SystemExit('recognize_ledger_openai anchor not found')
s = s.replace(ledger_anchor, helpers.strip('\n') + '\n\n' + ledger_anchor, 1)

new_ledger = r'''def recognize_ledger_openai(frame, config):
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

    # Accuracy first for the fixed ledger form: use the configured stronger
    # fallback model as the normal ledger model, while general mail remains unchanged.
    primary = str(config.get("model", OPENAI_DEFAULT_MODEL) or OPENAI_DEFAULT_MODEL).strip()
    stronger = str(config.get("fallback_model", "") or "").strip()
    ledger_model = stronger if stronger and stronger != primary else primary

    output_text = _call_openai_vision(
        config,
        ledger_model,
        OPENAI_LEDGER_PROMPT,
        image,
        "ledger_recognition_v223",
        LEDGER_SCHEMA,
        max_output_tokens=110,
        max_side=1800,
    )
    result = _parse_openai_ledger_json(output_text)
    result["institution"] = normalize_ledger_address(result.get("institution", ""))
    result["source"] = f"OpenAI Vision ({ledger_model})"

    image = None
    document = None
    return result
'''
s = replace_top_function(s, 'recognize_ledger_openai', new_ledger)

# ------------------------------------------------------------------
# EXCEL DISPLAY ONLY
# Preserve workbook/template/data semantics. Do not merge/unmerge cells and do
# not change template fonts globally. The requested view is: address starts at
# the left edge and long text shrinks within its existing cell/merged range.
# ------------------------------------------------------------------
format_helper = r'''def _apply_postal_excel_display(sheet, row):
    address_range = sheet.Range(f"F{row}:I{row}")
    recipient_cell = sheet.Range(f"{RECIPIENT_COLUMN}{row}")

    # Excel constants: xlLeft=-4131, xlCenter=-4108
    address_range.HorizontalAlignment = -4131
    address_range.VerticalAlignment = -4108
    address_range.WrapText = False
    address_range.ShrinkToFit = True
    try:
        address_range.IndentLevel = 0
    except Exception:
        pass

    recipient_cell.HorizontalAlignment = -4108
    recipient_cell.VerticalAlignment = -4108
    recipient_cell.WrapText = False
    recipient_cell.ShrinkToFit = True
'''

write_seg = top_function_segment(s, 'write_excel')
old_write = '''        sheet.Range(f"{ADDRESS_COLUMN}{row}").Value = address\n        sheet.Range(f"{RECIPIENT_COLUMN}{row}").Value = recipient\n\n        workbook.Save()'''
new_write = '''        sheet.Range(f"{ADDRESS_COLUMN}{row}").Value = address\n        sheet.Range(f"{RECIPIENT_COLUMN}{row}").Value = recipient\n        _apply_postal_excel_display(sheet, row)\n\n        workbook.Save()'''
if old_write not in write_seg:
    raise SystemExit('write_excel assignment anchor not found')
write_seg = write_seg.replace(old_write, new_write, 1)
s = replace_top_function(s, 'write_excel', write_seg)

# Insert helper immediately before write_excel after function replacement.
write_anchor = 'def write_excel(excel_file, recipient, address):'
if write_anchor not in s:
    raise SystemExit('write_excel anchor missing after replacement')
s = s.replace(write_anchor, format_helper.strip('\n') + '\n\n' + write_anchor, 1)

# ------------------------------------------------------------------
# FINAL PRESERVATION CHECKS
# ------------------------------------------------------------------
ui_after = class_segment(s, 'PostalScannerApp')
if hashlib.sha256(ui_before.encode('utf-8')).digest() != hashlib.sha256(ui_after.encode('utf-8')).digest():
    raise SystemExit('UI preservation failure: PostalScannerApp changed')

for name, before in protected_before.items():
    after = top_function_segment(s, name)
    if before != after:
        raise SystemExit(f'protected settings/data function changed: {name}')

required_after = [
    'APP_VERSION = "2.2.3"',
    'DATA_DIR = PERSISTENT_ROOT / "data"',
    'OPENAI_SECURE_KEY_FILE = DATA_DIR / "openai_key.dat"',
    'PRIVACY_MAX_EXTERNAL_RATIO_LEDGER = 0.58',
    '"store": False',
    'def _build_ledger_focus_image(',
    'def _apply_postal_excel_display(',
    'address_range.HorizontalAlignment = -4131',
    'recipient_cell.ShrinkToFit = True',
]
missing_after = [x for x in required_after if x not in s]
if missing_after:
    raise SystemExit('2.2.3 patch contract missing: ' + repr(missing_after))

if 'cv2.imwrite(' in s:
    raise SystemExit('captured-image disk write detected')

p.write_text(s, encoding='utf-8')
print('2.2.3 ledger/excel patch applied; UI/settings/data preserved byte-for-byte')
