# -*- coding: utf-8 -*-
"""
PostalScanner Updater

- HTTPS ZIP 다운로드
- SHA-256 무결성 검증
- 업무데이터/설정파일은 건드리지 않음
- 기존 프로그램 파일 자동 백업
- 설치 실패 시 자동 롤백
- 완료 후 PostalScanner 재실행
"""

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import zipfile
from pathlib import Path
from urllib.request import Request, urlopen

PRESERVE_NAMES = {
    # 업무/설정 데이터는 업데이트 패키지로 덮어쓰거나 삭제하지 않는다.
    "output",
    "audit",
    "metrics",
    "original",
    "openai_config.json",
    "openai_key.dat",  # 2.1.0 Windows DPAPI 암호화 API Key
    "address_aliases.json",
    "clova_config.json",
    "update_config.json",

    # 실행 중인 Updater 자체는 Windows에서 잠길 수 있으므로 보존한다.
    # Updater 자체 업데이트는 추후 별도 교체 단계에서 처리한다.
    "PostalScanner_Updater.py",
    "PostalScanner_Updater.exe",
}


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            chunk = f.read(1024 * 1024)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest().lower()


def download_https(url, destination):
    if not str(url).lower().startswith("https://"):
        raise RuntimeError("HTTPS 업데이트만 허용됩니다.")
    req = Request(url, headers={"User-Agent": "PostalScanner-Updater"})
    with urlopen(req, timeout=60) as response, open(destination, "wb") as out:
        while True:
            chunk = response.read(1024 * 1024)
            if not chunk:
                break
            out.write(chunk)


def safe_extract_zip(zip_path, destination):
    destination = Path(destination).resolve()
    with zipfile.ZipFile(zip_path, "r") as zf:
        for member in zf.infolist():
            target = (destination / member.filename).resolve()
            if os.path.commonpath([str(destination), str(target)]) != str(destination):
                raise RuntimeError("안전하지 않은 업데이트 ZIP 경로가 감지되었습니다.")
        zf.extractall(destination)


def effective_stage_root(stage):
    items = [p for p in Path(stage).iterdir() if p.name not in ("__MACOSX",)]
    if len(items) == 1 and items[0].is_dir():
        return items[0]
    return Path(stage)


def copy_tree_filtered(source, destination, preserve=False):
    source = Path(source)
    destination = Path(destination)
    destination.mkdir(parents=True, exist_ok=True)

    for item in source.iterdir():
        if item.name in PRESERVE_NAMES:
            continue
        dst = destination / item.name
        if item.is_dir():
            if dst.exists() and not preserve:
                shutil.rmtree(dst, ignore_errors=True)
            shutil.copytree(item, dst, dirs_exist_ok=True)
        else:
            shutil.copy2(item, dst)


def clear_program_files(target):
    target = Path(target)
    for item in list(target.iterdir()):
        if item.name in PRESERVE_NAMES:
            continue
        try:
            if item.is_dir():
                shutil.rmtree(item)
            else:
                item.unlink()
        except FileNotFoundError:
            pass


def make_backup(target, backup):
    target = Path(target)
    backup = Path(backup)
    if backup.exists():
        shutil.rmtree(backup, ignore_errors=True)
    backup.mkdir(parents=True, exist_ok=True)
    copy_tree_filtered(target, backup, preserve=True)


def restore_backup(target, backup):
    clear_program_files(target)
    copy_tree_filtered(backup, target, preserve=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--target-dir", required=True)
    parser.add_argument("--package-url", required=True)
    parser.add_argument("--sha256", required=True)
    parser.add_argument("--restart-json", required=True)
    args = parser.parse_args()

    target = Path(args.target_dir).resolve()
    expected = args.sha256.strip().lower()
    if len(expected) != 64 or any(c not in "0123456789abcdef" for c in expected):
        raise RuntimeError("SHA-256 값이 올바르지 않습니다.")

    restart_cmd = json.loads(args.restart_json)
    if not isinstance(restart_cmd, list) or not restart_cmd:
        raise RuntimeError("재시작 명령이 올바르지 않습니다.")

    backup = target.parent / (target.name + "_UPDATE_BACKUP")

    with tempfile.TemporaryDirectory(prefix="PostalScanner_Update_") as temp_dir:
        temp = Path(temp_dir)
        package = temp / "update.zip"
        stage = temp / "stage"
        stage.mkdir(parents=True, exist_ok=True)

        download_https(args.package_url, package)
        actual = sha256_file(package)
        if actual != expected:
            raise RuntimeError("업데이트 파일 SHA-256 검증에 실패했습니다.")

        safe_extract_zip(package, stage)
        stage_root = effective_stage_root(stage)

        # 본 프로그램이 완전히 종료될 시간을 준다.
        time.sleep(1.4)

        make_backup(target, backup)
        try:
            clear_program_files(target)
            copy_tree_filtered(stage_root, target)
        except Exception:
            restore_backup(target, backup)
            raise

    # 설치가 끝난 경우에만 재실행
    subprocess.Popen(restart_cmd, cwd=str(target))


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        # updater는 개인정보를 다루지 않으므로 오류 종류만 간단히 표시한다.
        try:
            import tkinter as tk
            from tkinter import messagebox
            root = tk.Tk()
            root.withdraw()
            messagebox.showerror(
                "PostalScanner 업데이트 실패",
                "업데이트를 완료하지 못했습니다. 기존 버전은 가능한 경우 자동 복구되었습니다.\n\n" + str(e),
            )
            root.destroy()
        except Exception:
            pass
        sys.exit(1)
