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


def replace_fn(source, name, replacement):
    node = fn_node(source, name)
    lines = source.splitlines()
    lines[node.lineno - 1:node.end_lineno] = replacement.rstrip('\n').splitlines()
    return '\n'.join(lines) + '\n'


required = [
    'APP_VERSION = "2.2.4"',
    'PERSISTENT_ROOT = get_persistent_root()',
    'DATA_DIR = PERSISTENT_ROOT / "data"',
    'OPENAI_SECURE_KEY_FILE = DATA_DIR / "openai_key.dat"',
    'PRIVACY_MODE = True',
    'ledger_recognition_v224_context',
    'def open_management(self):',
    'def _apply_postal_excel_display(',
]
missing = [x for x in required if x not in s]
if missing:
    raise SystemExit('2.2.4 preserved source mismatch: ' + repr(missing))

# Preserve everything except the display/page-setup helper and the version.
ui_before = segment(s, class_node(s, 'PostalScannerApp'))
protected_names = [
    'get_persistent_root',
    '_copy_legacy_data_once',
    'save_secure_openai_api_key',
    'load_secure_openai_api_key',
    'load_openai_config',
    'load_update_config',
    'recognize_general_openai',
    'recognize_ledger_openai',
    'write_excel',
]
protected_before = {name: segment(s, fn_node(s, name)) for name in protected_names}

s, count = re.subn(r'APP_VERSION\s*=\s*"2\.2\.4"', 'APP_VERSION = "2.2.5"', s, count=1)
if count != 1:
    raise SystemExit('APP_VERSION 2.2.4 anchor not found')

new_helper = r'''def _apply_postal_excel_display(sheet, row):
    """Keep row text readable and force the postal form to one A4 print page."""
    address_range = sheet.Range(f"F{row}:I{row}")
    recipient_cell = sheet.Range(f"{RECIPIENT_COLUMN}{row}")

    # Existing requested display behavior.
    # Excel constants: xlLeft=-4131, xlCenter=-4108
    address_range.HorizontalAlignment = -4131
    address_range.VerticalAlignment = -4108
    address_range.WrapText = False
    address_range.ShrinkToFit = True

    recipient_cell.HorizontalAlignment = -4108
    recipient_cell.VerticalAlignment = -4108
    recipient_cell.WrapText = False
    recipient_cell.ShrinkToFit = True

    # Print contract for the original postal form.
    # A1:K49 contains the complete one-page form including the lower summary area.
    # Force 1 page wide x 1 page tall so printer defaults cannot split/crop it.
    try:
        sheet.ResetAllPageBreaks()
    except Exception:
        pass

    try:
        page = sheet.PageSetup
    except Exception:
        page = None

    if page is not None:
        settings = (
            ('PrintArea', '$A$1:$K$49'),
            ('Zoom', False),
            ('FitToPagesWide', 1),
            ('FitToPagesTall', 1),
            ('Orientation', 1),      # xlPortrait
            ('PaperSize', 9),        # xlPaperA4
            ('CenterHorizontally', True),
            ('CenterVertically', False),
            ('LeftMargin', 18.0),    # 0.25 inch
            ('RightMargin', 18.0),
            ('TopMargin', 18.0),
            ('BottomMargin', 18.0),
            ('HeaderMargin', 0.0),
            ('FooterMargin', 0.0),
        )
        for name, value in settings:
            try:
                setattr(page, name, value)
            except Exception:
                # Some printer drivers reject individual properties. Keep applying
                # the remaining one-page settings instead of losing the data write.
                pass
'''
s = replace_fn(s, '_apply_postal_excel_display', new_helper)

# Preservation guards.
ui_after = segment(s, class_node(s, 'PostalScannerApp'))
if hashlib.sha256(ui_before.encode('utf-8')).hexdigest() != hashlib.sha256(ui_after.encode('utf-8')).hexdigest():
    raise SystemExit('UI/settings changed unexpectedly')

for name, before in protected_before.items():
    after = segment(s, fn_node(s, name))
    if before != after:
        raise SystemExit(f'protected function changed unexpectedly: {name}')

if 'shutil.move(' in s:
    raise SystemExit('destructive migration call detected')
if 'cv2.imwrite(' in s:
    raise SystemExit('captured image disk write detected')

helper = segment(s, fn_node(s, '_apply_postal_excel_display'))
for token in (
    "('PrintArea', '$A$1:$K$49')",
    "('Zoom', False)",
    "('FitToPagesWide', 1)",
    "('FitToPagesTall', 1)",
    "('Orientation', 1)",
    "('PaperSize', 9)",
    'sheet.ResetAllPageBreaks()',
):
    if token not in helper:
        raise SystemExit('missing print contract token: ' + token)

p.write_text(s, encoding='utf-8')
print('2.2.5 one-page A4 print patch applied; recognition/UI/settings/data/updater preserved')
