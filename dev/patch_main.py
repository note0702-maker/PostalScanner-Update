from pathlib import Path
import ast

p = Path('src/PostalScanner.py')
s = p.read_text(encoding='utf-8')

remove_top = {
    'load_clova_config',
    'is_ascii_path','model_root','create_paddle_ocr','warmup_paddle','paddle_read',
    'extract_general_recipient','general_is_postcode','general_address_start','general_detail_line',
    'general_address_line_score','general_result_quality','extract_general_address',
    'extract_ledger_lower_crop','encode_png_base64','clova_ocr_crop','hangul_only','normalized_hangul',
    'enhance_handwriting_image','threshold_handwriting_image','merge_clova_fields','clova_general_rows',
    'is_ledger_handwriting_candidate','cluster_ledger_fields_by_y','crop_ledger_bottom_band',
    'clean_ledger_fragment','normalize_admin_spacing','ledger_base_key','apply_ledger_suffix',
    'nearest_suffix_for_ledger_field','add_suffix_once','reconstruct_ledger_from_lower_fields',
    'ledger_candidate_score','recognize_ledger_partial',
}
remove_methods = {'paddle_worker'}

tree = ast.parse(s)
ranges = []
for node in tree.body:
    if isinstance(node, ast.FunctionDef) and node.name in remove_top:
        ranges.append((node.lineno, node.end_lineno))
    if isinstance(node, ast.ClassDef):
        for child in node.body:
            if isinstance(child, ast.FunctionDef) and child.name in remove_methods:
                ranges.append((child.lineno, child.end_lineno))

lines = s.splitlines()
for start, end in sorted(ranges, reverse=True):
    del lines[start-1:end]
s = '\n'.join(lines) + '\n'

s = s.replace('PostalScanner 2.1.0\n\n고정 구조', 'PostalScanner 2.2.0-dev\n\n고정 구조', 1)
s = s.replace('APP_VERSION = "2.1.2"', 'APP_VERSION = "2.2.0-dev"', 1)
s = s.replace('import uuid\n', '')
s = s.replace('import subprocess\n', 'import subprocess\nimport shutil\nimport tempfile\n')
s = s.replace('from urllib.error import HTTPError, URLError\n', 'from urllib.error import HTTPError, URLError\nfrom urllib.parse import quote\n')

import_anchor = 'from tkinter import ttk, messagebox, simpledialog\n'
rule_import = '''from postal_rules import (\n    GENERAL_MAIL_PROMPT,\n    LEDGER_PROMPT,\n    normalize_general_result,\n    general_address_has_structure,\n    ledger_name_is_plausible,\n)\n'''
s = s.replace(import_anchor, import_anchor + '\n' + rule_import, 1)

s = s.replace('PaddleOCR = None\n', '')
s = s.replace('\nCLOVA_TIMEOUT_SEC = 20\n', '\n')
s = s.replace('MODEL_DIR = BASE_DIR / "models"\n', '')

if 'MODEL_NAMES = {' in s:
    start = s.index('MODEL_NAMES = {')
    end = s.index('\n}\n', start) + 3
    s = s[:start] + s[end:]

start_marker = '# ============================================================\n# CLOVA 설정\n'
if start_marker in s:
    start = s.index(start_marker)
    end_marker = '# ============================================================\n# OpenAI 설정 - 일반 우편물 + 인감대장송부 공통\n'
    end = s.index(end_marker, start)
    s = s[:start] + s[end:]

s = s.replace(
    'UPDATE_USER_AGENT = f"PostalScanner-Updater-Check/{APP_VERSION}"',
    'UPDATE_USER_AGENT = f"PostalScanner-Updater-Check/{APP_VERSION}"\nDEFAULT_UPDATE_MANIFEST_URL = "https://raw.githubusercontent.com/note0702-maker/PostalScanner-Update/main/update_manifest.json"',
    1,
)
old_update_cfg = '''def load_update_config():\n    """\n    EXE/PY 옆 update_config.json을 읽는다.\n    설정이 없으면 프로그램 기능은 그대로 사용하고 자동업데이트만 비활성화한다.\n    """\n    if not UPDATE_CONFIG_FILE.exists():\n        return {"enabled": False, "manifest_url": ""}\n\n    try:\n        data = json.loads(UPDATE_CONFIG_FILE.read_text(encoding="utf-8"))\n    except Exception:\n        return {"enabled": False, "manifest_url": ""}\n\n    enabled = bool(data.get("enabled", True))\n    manifest_url = str(data.get("manifest_url", "")).strip()\n    return {\n        "enabled": enabled,\n        "manifest_url": manifest_url,\n    }\n'''
new_update_cfg = '''def load_update_config():\n    """내장 manifest를 기본 사용한다. update_config.json은 비상용 선택 override다."""\n    if not UPDATE_CONFIG_FILE.exists():\n        return {"enabled": True, "manifest_url": DEFAULT_UPDATE_MANIFEST_URL}\n\n    try:\n        data = json.loads(UPDATE_CONFIG_FILE.read_text(encoding="utf-8"))\n        if not isinstance(data, dict):\n            raise ValueError("not a dict")\n    except Exception:\n        return {"enabled": True, "manifest_url": DEFAULT_UPDATE_MANIFEST_URL}\n\n    enabled = bool(data.get("enabled", True))\n    manifest_url = str(data.get("manifest_url", "") or DEFAULT_UPDATE_MANIFEST_URL).strip()\n    return {"enabled": enabled, "manifest_url": manifest_url}\n'''
if old_update_cfg not in s:
    raise SystemExit('load_update_config anchor missing')
s = s.replace(old_update_cfg, new_update_cfg, 1)

old_general_prompt_start = 'OPENAI_GENERAL_PROMPT = r"""\n'
if old_general_prompt_start in s:
    st = s.index(old_general_prompt_start)
    en = s.index('\n"""\n\nGENERAL_SCHEMA', st) + len('\n"""')
    s = s[:st] + 'OPENAI_GENERAL_PROMPT = GENERAL_MAIL_PROMPT' + s[en:]

old_ledger_prompt_start = 'OPENAI_LEDGER_PROMPT = r"""\n'
if old_ledger_prompt_start in s:
    st = s.index(old_ledger_prompt_start)
    en = s.index('\n"""\n\nLEDGER_SCHEMA', st) + len('\n"""')
    s = s[:st] + 'OPENAI_LEDGER_PROMPT = LEDGER_PROMPT' + s[en:]

needle = '''    address = str(obj.get("address", "") or "").strip()\n    name = str(obj.get("name", "") or "").strip()\n    name = re.sub(r"\\s*(귀하|님|선생님)\\s*$", "", name).strip()\n'''
repl = '''    address = str(obj.get("address", "") or "").strip()\n    name = str(obj.get("name", "") or "").strip()\n    address, name = normalize_general_result(address, name)\n'''
if needle not in s:
    raise SystemExit('general parse anchor missing')
s = s.replace(needle, repl, 1)

needle = '''    if ac < 0.78 or nc < 0.78:\n        return True\n    if not re.search(r"[가-힣0-9]", address):\n        return True\n    return False\n'''
repl = '''    if ac < 0.78 or nc < 0.78:\n        return True\n    if not re.search(r"[가-힣0-9]", address):\n        return True\n    if not general_address_has_structure(address) and not re.search(\n        r"(특별시|광역시|특별자치시|특별자치도|도)", address\n    ):\n        return True\n    return False\n'''
if needle not in s:
    raise SystemExit('general retry anchor missing')
s = s.replace(needle, repl, 1)

needle = '''    if conf < 0.80:\n        return True\n    if not re.search(r"(도|시|군|구|읍|면|동|장)", address):\n        return True\n    return False\n'''
repl = '''    if conf < 0.80:\n        return True\n    if not re.search(r"(도|시|군|구|읍|면|동|장)", address):\n        return True\n    if not ledger_name_is_plausible(name):\n        return True\n    return False\n'''
if needle not in s:
    raise SystemExit('ledger retry anchor missing')
s = s.replace(needle, repl, 1)

start = s.index('def openai_diagnostic_check(config):')
end = s.index('\n\ndef write_general_count', start)
new_diag = '''def openai_diagnostic_check(config):\n    """개인정보/이미지/생성요청 없이 API Key와 선택 모델 접근만 확인한다."""\n    if not config or not str(config.get("api_key", "") or "").strip():\n        return False, "API Key 설정 필요"\n\n    model = str(config.get("model", OPENAI_DEFAULT_MODEL) or OPENAI_DEFAULT_MODEL).strip()\n    model_url = "https://api.openai.com/v1/models/" + quote(model, safe="")\n    request = Request(\n        model_url,\n        method="GET",\n        headers={\n            "Authorization": "Bearer " + config["api_key"],\n            "Accept": "application/json",\n        },\n    )\n    try:\n        with urlopen(request, timeout=min(OPENAI_TIMEOUT_SEC, 15)) as response:\n            response.read(32 * 1024)\n            if 200 <= int(getattr(response, "status", 200)) < 300:\n                return True, f"인증/모델 접근 정상 · {model}"\n    except HTTPError as e:\n        code = int(getattr(e, "code", 0) or 0)\n        if code == 401:\n            return False, "API Key 인증 실패"\n        if code == 403:\n            return False, "API 권한 확인 필요"\n        if code == 404:\n            return False, f"모델 접근 확인 필요 · {model}"\n        if code == 429:\n            return False, "사용량/결제 한도 확인"\n        return False, f"OpenAI HTTP {code}"\n    except (URLError, TimeoutError, OSError):\n        return False, "네트워크 연결 확인"\n    except Exception:\n        return False, "OpenAI 연결 확인 필요"\n    return False, "응답 확인 필요"\n'''
s = s[:start] + new_diag + s[end:]

s = s.replace('        self.paddle_ready = True\n', '')
s = s.replace('        self.paddle_load_progress = 0\n', '')
s = s.replace('        self.paddle = None\n', '')
s = s.replace('        self.clova_config = None\n', '')

paddle_branch = '''\n        elif component == "paddle":\n            self.paddle_load_progress = value\n\n            if text:\n                self.paddle_state.config(\n                    text=f"PaddleOCR: {text}",\n                    fg=(\n                        "#75dc92"\n                        if value >= 100\n                        else self.orange\n                    ),\n                )\n'''
s = s.replace(paddle_branch, '')

deep_button = '''        self.deep_health_button = tk.Button(\n            bottom_actions,\n            text="정밀 점검",\n            command=self.show_deep_system_health,\n            font=("맑은 고딕", 8, "bold"),\n            bg="#374151",\n            fg="white",\n            relief="flat",\n        )\n        self.deep_health_button.pack(side="left", padx=(0, 6), ipadx=6, ipady=5)\n\n'''
s = s.replace(deep_button, '')
s = s.replace('text="시스템 점검",\n            command=self.show_system_health,', 'text="시스템 점검",\n            command=self.show_deep_system_health,', 1)
s = s.replace('self.deep_health_button.config(state="disabled", text="점검 중...")', 'self.health_button.config(state="disabled", text="점검 중...")')
s = s.replace('self.deep_health_button.config(state="normal", text="정밀 점검")', 'self.health_button.config(state="normal", text="시스템 점검")')

s = s.replace(
    '(BASE_DIR / "PostalScanner_Updater.exe").exists() or (BASE_DIR / "PostalScanner_Updater.py").exists()',
    '(BASE_DIR / "updater" / "PostalScanner_Updater.exe").exists() or (BASE_DIR / "PostalScanner_Updater.exe").exists()',
)

anchor = 'def build_restart_command():\n'
helper = '''def prepare_external_updater():\n    """Updater를 설치 폴더 밖 TEMP로 복사해 현재 설치 폴더를 안전하게 교체할 수 있게 한다."""\n    candidates = [\n        BASE_DIR / "updater" / "PostalScanner_Updater.exe",\n        BASE_DIR / "PostalScanner_Updater.exe",\n    ]\n    source_exe = next((p for p in candidates if p.exists()), None)\n    if source_exe is None:\n        raise RuntimeError("PostalScanner Updater를 찾지 못했습니다.")\n\n    runner_root = Path(tempfile.mkdtemp(prefix="PostalScanner_Updater_Run_"))\n    if source_exe.parent.name.lower() == "updater":\n        runner_dir = runner_root / "updater"\n        shutil.copytree(source_exe.parent, runner_dir)\n        runner_exe = runner_dir / source_exe.name\n    else:\n        runner_exe = runner_root / source_exe.name\n        shutil.copy2(source_exe, runner_exe)\n    return runner_exe\n\n\n'''
s = s.replace(anchor, helper + anchor, 1)

start = s.index('    def install_pending_update(self):')
end = s.index('    def shutdown_for_update(self):', start)
new_install = '''    def install_pending_update(self):\n        manifest = self.pending_update\n        if not manifest:\n            return\n\n        if not getattr(sys, "frozen", False):\n            messagebox.showwarning(\n                "개발 실행에서는 업데이트 설치 불가",\n                "자동업데이트 설치는 PostalScanner.exe에서만 실행됩니다.",\n            )\n            return\n\n        if self.processing or self.excel_busy:\n            messagebox.showwarning(\n                "처리 중",\n                "현재 인식/Excel 작업이 끝난 뒤 업데이트해주세요.",\n            )\n            return\n\n        try:\n            updater_exe = prepare_external_updater()\n        except Exception:\n            messagebox.showerror(\n                "업데이트 구성 필요",\n                "안전 업데이트 실행기를 준비하지 못했습니다. 현재 버전은 그대로 유지됩니다.",\n            )\n            return\n\n        restart_json = json.dumps([str(BASE_DIR / "PostalScanner.exe")], ensure_ascii=False)\n        command = [\n            str(updater_exe),\n            "--target-dir", str(BASE_DIR),\n            "--package-url", manifest["package_url"],\n            "--sha256", manifest["sha256"],\n            "--restart-json", restart_json,\n            "--wait-pid", str(os.getpid()),\n        ]\n        try:\n            subprocess.Popen(command, cwd=str(updater_exe.parent), close_fds=(os.name != "nt"))\n        except Exception:\n            messagebox.showerror(\n                "업데이트 실행 실패",\n                "업데이트 프로그램을 시작하지 못했습니다. 현재 버전을 계속 사용합니다.",\n            )\n            return\n        audit("업데이트 설치 시작", f"from={APP_VERSION}, to={manifest['version']}")\n        self.shutdown_for_update()\n\n'''
s = s[:start] + new_install + s[end:]

shutdown_start = s.index('    def shutdown_for_update(self):')
close_start = s.index('    def close(self):', shutdown_start)
if '_cancel_pending_tk_after_callbacks' not in s:
    helper_method = '''    def _cancel_pending_tk_after_callbacks(self):\n        try:\n            pending = self.root.tk.call("after", "info")\n            if isinstance(pending, str):\n                pending = self.root.tk.splitlist(pending)\n            for token in tuple(pending or ()):\n                try:\n                    self.root.after_cancel(token)\n                except Exception:\n                    pass\n        except Exception:\n            pass\n\n'''
    s = s[:shutdown_start] + helper_method + s[shutdown_start:]
    shutdown_start = s.index('    def shutdown_for_update(self):')
    close_start = s.index('    def close(self):', shutdown_start)

new_shutdown = '''    def shutdown_for_update(self):\n        """업데이트용 종료. 당일 Excel/사용자 데이터는 삭제하지 않는다."""\n        self.running = False\n        try:\n            self.root.unbind_all("<KeyPress-space>")\n        except Exception:\n            pass\n        self._cancel_pending_tk_after_callbacks()\n        remove_session_lock()\n        release_single_instance()\n        with self.camera_lock:\n            if self.camera is not None:\n                try:\n                    self.camera.release()\n                except Exception:\n                    pass\n                self.camera = None\n        try:\n            self.root.quit()\n        except Exception:\n            pass\n        try:\n            self.root.destroy()\n        except Exception:\n            pass\n\n'''
s = s[:shutdown_start] + new_shutdown + s[close_start:]

old = '''        self.root.after(\n            30,\n            self.update_camera,\n        )\n\n    def capture_best_frame(self):\n'''
new = '''        if self.running:\n            try:\n                self.root.after(30, self.update_camera)\n            except tk.TclError:\n                pass\n\n    def capture_best_frame(self):\n'''
if old in s:
    s = s.replace(old, new, 1)

s = s.replace('f"{APP_VERSION} · 단일실행 · 비정상복구 · Excel검증 · DPAPI · 저신뢰확인 · 정밀점검 · 자동업데이트"',
              'f"{APP_VERSION} · OpenAI 전용 · 판독규칙 보존 · Excel검증 · DPAPI · 안전업데이트"')
s = s.replace('# PaddleOCR/CLOVA 로딩 없음 - 두 모드 모두 OpenAI Vision 사용', '# OpenAI-only: 로컬 OCR/CLOVA 엔진을 로딩하지 않는다.')

p.write_text(s, encoding='utf-8')
