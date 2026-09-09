from pathlib import Path

p = Path('src/PostalScanner.py')
s = p.read_text(encoding='utf-8')

# Version / visible identity
s = s.replace('PostalScanner 2.1.0', 'PostalScanner 2.2.0 DEV PREVIEW', 1)
s = s.replace('APP_VERSION = "2.1.2"', 'APP_VERSION = "2.2.0-dev"', 1)

# Shared business-rule module. The OCR engine remains OpenAI-only in the active paths.
anchor = 'from urllib.error import HTTPError, URLError\n'
if 'from urllib.parse import quote' not in s:
    s = s.replace(anchor, anchor + 'from urllib.parse import quote\n', 1)

anchor = 'from tkinter import ttk, messagebox, simpledialog\n'
rule_import = '''\nfrom postal_rules import (\n    GENERAL_MAIL_PROMPT,\n    LEDGER_PROMPT,\n    normalize_general_result,\n    general_address_has_structure,\n    ledger_name_is_plausible,\n)\n'''
if 'from postal_rules import (' not in s:
    s = s.replace(anchor, anchor + rule_import, 1)

# Replace OpenAI prompts with preserved official rules.
def replace_prompt(var_name, replacement):
    global s
    marker = var_name + ' = r"""\n'
    if marker not in s:
        return
    st = s.index(marker)
    en = s.index('\n"""', st) + len('\n"""')
    s = s[:st] + f'{var_name} = {replacement}' + s[en:]

replace_prompt('OPENAI_GENERAL_PROMPT', 'GENERAL_MAIL_PROMPT')
replace_prompt('OPENAI_LEDGER_PROMPT', 'LEDGER_PROMPT')

# Apply preserved K/T + honorific rules to every OpenAI general result.
old = '''    address = str(obj.get("address", "") or "").strip()\n    name = str(obj.get("name", "") or "").strip()\n    name = re.sub(r"\\s*(귀하|님|선생님)\\s*$", "", name).strip()\n'''
new = '''    address = str(obj.get("address", "") or "").strip()\n    name = str(obj.get("name", "") or "").strip()\n    address, name = normalize_general_result(address, name)\n'''
if old in s:
    s = s.replace(old, new, 1)

# Retry rules: allow omitted province when the remaining address structure is valid.
old = '''    if ac < 0.78 or nc < 0.78:\n        return True\n    if not re.search(r"[가-힣0-9]", address):\n        return True\n    return False\n'''
new = '''    if ac < 0.78 or nc < 0.78:\n        return True\n    if not re.search(r"[가-힣0-9]", address):\n        return True\n    if not general_address_has_structure(address) and not re.search(\n        r"(특별시|광역시|특별자치시|특별자치도|도)", address\n    ):\n        return True\n    return False\n'''
if old in s:
    s = s.replace(old, new, 1)

old = '''    if conf < 0.80:\n        return True\n    if not re.search(r"(도|시|군|구|읍|면|동|장)", address):\n        return True\n    return False\n'''
new = '''    if conf < 0.80:\n        return True\n    if not re.search(r"(도|시|군|구|읍|면|동|장)", address):\n        return True\n    if not ledger_name_is_plausible(name):\n        return True\n    return False\n'''
if old in s:
    s = s.replace(old, new, 1)

# Fix diagnostic HTTP 400: verify API key + selected model using model metadata GET.
st = s.index('def openai_diagnostic_check(config):')
en = s.index('\n\ndef write_general_count', st)
new_diag = '''def openai_diagnostic_check(config):\n    """개인정보/이미지/생성요청 없이 API Key와 선택 모델 접근만 확인한다."""\n    if not config or not str(config.get("api_key", "") or "").strip():\n        return False, "API Key 설정 필요"\n\n    model = str(config.get("model", OPENAI_DEFAULT_MODEL) or OPENAI_DEFAULT_MODEL).strip()\n    request = Request(\n        "https://api.openai.com/v1/models/" + quote(model, safe=""),\n        method="GET",\n        headers={\n            "Authorization": "Bearer " + config["api_key"],\n            "Accept": "application/json",\n        },\n    )\n    try:\n        with urlopen(request, timeout=min(OPENAI_TIMEOUT_SEC, 15)) as response:\n            response.read(32 * 1024)\n            if 200 <= int(getattr(response, "status", 200)) < 300:\n                return True, f"인증/모델 접근 정상 · {model}"\n    except HTTPError as e:\n        code = int(getattr(e, "code", 0) or 0)\n        if code == 401:\n            return False, "API Key 인증 실패"\n        if code == 403:\n            return False, "API 권한 확인 필요"\n        if code == 404:\n            return False, f"모델 접근 확인 필요 · {model}"\n        if code == 429:\n            return False, "사용량/결제 한도 확인"\n        return False, f"OpenAI HTTP {code}"\n    except (URLError, TimeoutError, OSError):\n        return False, "네트워크 연결 확인"\n    except Exception:\n        return False, "OpenAI 연결 확인 필요"\n    return False, "응답 확인 필요"\n'''
s = s[:st] + new_diag + s[en:]

# UI label only; stable updater/manifest are not changed by this DEV build.
s = s.replace(
    'f"{APP_VERSION} · 단일실행 · 비정상복구 · Excel검증 · DPAPI · 저신뢰확인 · 정밀점검 · 자동업데이트"',
    'f"{APP_VERSION} · OpenAI 전용 · 기존 판독조건 보존 · DEV PREVIEW"',
)

p.write_text(s, encoding='utf-8')
