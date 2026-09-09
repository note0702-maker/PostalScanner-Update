from pathlib import Path
p=Path('src/PostalScanner.py')
s=p.read_text(encoding='utf-8')

s=s.replace('ADDRESS_ALIAS_FILE = BASE_DIR / "address_aliases.json" if "BASE_DIR" in globals() else None\n\n','')
old='''BASE_DIR = get_base_dir()
ORIGINAL_DIR = BASE_DIR / "original"
OUTPUT_DIR = BASE_DIR / "output"
AUDIT_DIR = BASE_DIR / "audit"
ADDRESS_ALIAS_FILE = BASE_DIR / "address_aliases.json"
UPDATE_CONFIG_FILE = BASE_DIR / UPDATE_CONFIG_NAME

# 2.1.0 실행/보안 상태 파일. 개인정보는 기록하지 않는다.
SESSION_LOCK_FILE = BASE_DIR / "session.lock"
OPENAI_SECURE_KEY_FILE = BASE_DIR / "openai_key.dat"
'''
new='''BASE_DIR = get_base_dir()
DATA_DIR = BASE_DIR / "data"
ORIGINAL_DIR = DATA_DIR / "original"
OUTPUT_DIR = DATA_DIR / "output"
AUDIT_DIR = DATA_DIR / "audit"
ADDRESS_ALIAS_FILE = DATA_DIR / "address_aliases.json"
OPENAI_CONFIG_FILE = DATA_DIR / "openai_config.json"
UPDATE_CONFIG_FILE = BASE_DIR / UPDATE_CONFIG_NAME  # 비상용 override만 지원
RESOURCE_TEMPLATE_FILE = BASE_DIR / "resources" / "요금후납_우편물_발송표_자동입력용.xlsx"

# 실행/보안 상태도 data 아래에 둬 프로그램 교체와 분리한다.
SESSION_LOCK_FILE = DATA_DIR / "session.lock"
OPENAI_SECURE_KEY_FILE = DATA_DIR / "openai_key.dat"
'''
if old not in s:
    raise SystemExit('path block not found')
s=s.replace(old,new,1)
s=s.replace('BASE_DIR / "openai_config.json"','OPENAI_CONFIG_FILE')

anchor='OUTPUT_DIR.mkdir(parents=True, exist_ok=True)\nAUDIT_DIR.mkdir(parents=True, exist_ok=True)\n'
helper='''def migrate_legacy_data_layout():
    """2.1.x 루트 데이터/설정을 2.2 data 폴더로 1회 이동한다."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    for name in ("original", "output", "audit", "metrics"):
        legacy = BASE_DIR / name
        target = DATA_DIR / name
        if legacy.exists() and not target.exists():
            try:
                shutil.move(str(legacy), str(target))
            except Exception:
                pass

    for name in ("openai_key.dat", "openai_config.json", "address_aliases.json"):
        legacy = BASE_DIR / name
        target = DATA_DIR / name
        if legacy.exists() and not target.exists():
            try:
                shutil.move(str(legacy), str(target))
            except Exception:
                try:
                    shutil.copy2(legacy, target)
                except Exception:
                    pass


def ensure_original_excel_seed():
    """원본 Excel이 전혀 없을 때만 배포 리소스의 깨끗한 양식을 복원한다."""
    ORIGINAL_DIR.mkdir(parents=True, exist_ok=True)
    existing = [p for p in ORIGINAL_DIR.glob("*.xlsx") if not p.name.startswith("~$")]
    if existing:
        return
    if RESOURCE_TEMPLATE_FILE.is_file():
        try:
            shutil.copy2(RESOURCE_TEMPLATE_FILE, ORIGINAL_DIR / RESOURCE_TEMPLATE_FILE.name)
        except Exception:
            pass


migrate_legacy_data_layout()
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
AUDIT_DIR.mkdir(parents=True, exist_ok=True)
ensure_original_excel_seed()
'''
if anchor not in s:
    raise SystemExit('mkdir anchor missing')
s=s.replace(anchor,helper,1)

s=s.replace('"HTTPS manifest 설정" if update_ok else "update_config.json 확인"','"내장 HTTPS manifest" if update_ok else "업데이트 manifest 확인"')
s=s.replace('add("업데이트 설정", False, "update_config.json 확인")','add("업데이트 설정", False, "업데이트 manifest 확인")')
s=s.replace('update_detail = "update_config.json 확인"','update_detail = "업데이트 manifest 확인"')
s=s.replace('lines = [f"PostalScanner {APP_VERSION} · 정밀 시스템 점검",', 'lines = [f"PostalScanner {APP_VERSION} · 시스템 점검",')
s=s.replace('"※ OpenAI 점검은 개인정보/이미지 없이 짧은 테스트 문장만 전송하며 store=false를 사용합니다."', '"※ OpenAI 점검은 개인정보/이미지/생성요청 없이 선택 모델 접근권한만 확인합니다."')
s=s.replace('messagebox.showinfo("PostalScanner 정밀 시스템 점검", text)','messagebox.showinfo("PostalScanner 시스템 점검", text)')
s=s.replace('messagebox.showwarning("처리 중", "현재 작업이 끝난 뒤 정밀 점검해주세요.")','messagebox.showwarning("처리 중", "현재 작업이 끝난 뒤 시스템 점검해주세요.")')
s=s.replace('# OpenAI-only: 로컬 OCR/CLOVA 엔진을 로딩하지 않는다.', '# OpenAI-only: 별도 로컬/클라우드 OCR 엔진을 로딩하지 않는다.')

p.write_text(s,encoding='utf-8')
