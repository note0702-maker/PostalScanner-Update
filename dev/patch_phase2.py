from pathlib import Path

p = Path('src/PostalScanner.py')
s = p.read_text(encoding='utf-8')

# 1) Safe data/template handling dependencies.
if 'import shutil\n' not in s:
    s = s.replace('import subprocess\n', 'import subprocess\nimport shutil\n', 1)

# 2) Separate replaceable app files from persistent user/work data.
old = '''BASE_DIR = get_base_dir()\nORIGINAL_DIR = BASE_DIR / "original"\nMODEL_DIR = BASE_DIR / "models"\nOUTPUT_DIR = BASE_DIR / "output"\nAUDIT_DIR = BASE_DIR / "audit"\nADDRESS_ALIAS_FILE = BASE_DIR / "address_aliases.json"\nUPDATE_CONFIG_FILE = BASE_DIR / UPDATE_CONFIG_NAME\n\n# 2.1.0 실행/보안 상태 파일. 개인정보는 기록하지 않는다.\nSESSION_LOCK_FILE = BASE_DIR / "session.lock"\nOPENAI_SECURE_KEY_FILE = BASE_DIR / "openai_key.dat"\n_SINGLE_INSTANCE_HANDLE = None\nUPDATER_STAGED_EXE = BASE_DIR / "PostalScanner_Updater_next.exe"\nUPDATER_STAGED_PY = BASE_DIR / "PostalScanner_Updater_next.py"\n'''
new = '''BASE_DIR = get_base_dir()\nDATA_DIR = BASE_DIR / "data"\nORIGINAL_DIR = DATA_DIR / "original"\nMODEL_DIR = BASE_DIR / "models"  # legacy compatibility only; active OCR is OpenAI-only\nOUTPUT_DIR = DATA_DIR / "output"\nAUDIT_DIR = DATA_DIR / "audit"\nADDRESS_ALIAS_FILE = DATA_DIR / "address_aliases.json"\nOPENAI_CONFIG_FILE = DATA_DIR / "openai_config.json"\nUPDATE_CONFIG_FILE = BASE_DIR / UPDATE_CONFIG_NAME  # emergency override only\nRESOURCE_DIR = BASE_DIR / "resources"\nRESOURCE_TEMPLATE_FILE = RESOURCE_DIR / "original_template.xlsx"\nORIGINAL_TEMPLATE_NAME = "요금후납_우편물_발송표_자동입력용.xlsx"\n\n# Runtime/security state is persistent data, not replaceable program code.\nSESSION_LOCK_FILE = DATA_DIR / "session.lock"\nOPENAI_SECURE_KEY_FILE = DATA_DIR / "openai_key.dat"\n_SINGLE_INSTANCE_HANDLE = None\nUPDATER_STAGED_EXE = BASE_DIR / "PostalScanner_Updater_next.exe"\nUPDATER_STAGED_PY = BASE_DIR / "PostalScanner_Updater_next.py"\n'''
if old not in s:
    raise SystemExit('phase2 path block not found')
s = s.replace(old, new, 1)

# All OpenAI config reads/writes now use persistent data path.
s = s.replace('BASE_DIR / "openai_config.json"', 'OPENAI_CONFIG_FILE')

# 3) Legacy data migration + template self-heal before folders are used.
old = '''OUTPUT_DIR.mkdir(parents=True, exist_ok=True)\nAUDIT_DIR.mkdir(parents=True, exist_ok=True)\n'''
new = '''def _copy_legacy_data_once():\n    """Copy 2.1.x root data into data/ without deleting rollback material."""\n    DATA_DIR.mkdir(parents=True, exist_ok=True)\n\n    for name in ("original", "output", "audit", "metrics"):\n        src = BASE_DIR / name\n        dst = DATA_DIR / name\n        if not src.exists() or dst.exists():\n            continue\n        try:\n            if src.is_dir():\n                shutil.copytree(src, dst)\n            else:\n                dst.parent.mkdir(parents=True, exist_ok=True)\n                shutil.copy2(src, dst)\n        except Exception:\n            pass\n\n    for name in ("openai_key.dat", "openai_config.json", "address_aliases.json"):\n        src = BASE_DIR / name\n        dst = DATA_DIR / name\n        if not src.is_file() or dst.exists():\n            continue\n        try:\n            dst.parent.mkdir(parents=True, exist_ok=True)\n            shutil.copy2(src, dst)\n        except Exception:\n            pass\n\n\ndef ensure_original_excel_seed():\n    """Restore a clean bundled Excel template only when no original workbook exists."""\n    ORIGINAL_DIR.mkdir(parents=True, exist_ok=True)\n    existing = [\n        item for item in ORIGINAL_DIR.glob("*.xlsx")\n        if item.is_file() and not item.name.startswith("~$")\n    ]\n    if existing:\n        return False\n    if not RESOURCE_TEMPLATE_FILE.is_file():\n        return False\n    try:\n        shutil.copy2(RESOURCE_TEMPLATE_FILE, ORIGINAL_DIR / ORIGINAL_TEMPLATE_NAME)\n        return True\n    except Exception:\n        return False\n\n\n_copy_legacy_data_once()\nOUTPUT_DIR.mkdir(parents=True, exist_ok=True)\nAUDIT_DIR.mkdir(parents=True, exist_ok=True)\nensure_original_excel_seed()\n'''
if old not in s:
    raise SystemExit('phase2 mkdir anchor not found')
s = s.replace(old, new, 1)

# 4) Diagnostics wording should reflect persistent data + auto-recovery.
s = s.replace(
    '"원본 Excel 또는 시트/셀 구조 확인 필요"',
    '"원본 Excel 자동복구 또는 시트/셀 구조 확인 필요"'
)

# 5) UI identity for this dev phase.
s = s.replace(
    'f"{APP_VERSION} · OpenAI 전용 · 기존 판독조건 보존 · DEV PREVIEW"',
    'f"{APP_VERSION} · OpenAI 전용 · 판독조건 보존 · data 분리 · Excel 자동복구 · DEV"',
    1,
)

p.write_text(s, encoding='utf-8')
