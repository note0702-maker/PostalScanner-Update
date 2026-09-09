# -*- coding: utf-8 -*-
"""PostalScanner 2.2 safe updater.

핵심 원칙
- 새 패키지를 완전히 다운로드/검증/압축해제하기 전 기존 설치를 건드리지 않는다.
- Updater는 설치 폴더 밖 TEMP에서 실행되어야 한다.
- 기존 설치 폴더는 삭제하지 않고 디렉터리 rename으로 백업한다.
- 새 PostalScanner.exe 존재를 확인한 뒤 교체한다.
- 새 앱 재시작 실패 시 기존 폴더를 즉시 롤백한다.
"""

import argparse
import ctypes
import hashlib
import json
import os
import queue
import shutil
import subprocess
import sys
import threading
import time
import zipfile
from pathlib import Path
from urllib.request import Request, urlopen

import tkinter as tk
from tkinter import ttk, messagebox

PRESERVE_NAMES = {
    "data",
    "output",
    "audit",
    "metrics",
    "original",
    "openai_config.json",
    "openai_key.dat",
    "address_aliases.json",
}

MIN_APP_EXE_BYTES = 100 * 1024


def _mb(value):
    return float(value or 0) / (1024.0 * 1024.0)


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest().lower()


def download_https(url, destination, progress=None):
    if not str(url).lower().startswith("https://"):
        raise RuntimeError("HTTPS 업데이트만 허용됩니다.")
    req = Request(url, headers={"User-Agent": "PostalScanner-Updater/2.2"})
    with urlopen(req, timeout=60) as response, open(destination, "wb") as out:
        try:
            total = int(response.headers.get("Content-Length") or 0)
        except Exception:
            total = 0
        downloaded = 0
        if progress:
            progress("download", downloaded=0, total=total)
        while True:
            chunk = response.read(1024 * 1024)
            if not chunk:
                break
            out.write(chunk)
            downloaded += len(chunk)
            if progress:
                progress("download", downloaded=downloaded, total=total)
    return downloaded, total


def safe_extract_zip(zip_path, destination, progress=None):
    destination = Path(destination).resolve()
    destination.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path, "r") as zf:
        members = zf.infolist()
        for member in members:
            target = (destination / member.filename).resolve()
            if os.path.commonpath([str(destination), str(target)]) != str(destination):
                raise RuntimeError("안전하지 않은 업데이트 ZIP 경로가 감지되었습니다.")
        count = max(1, len(members))
        for index, member in enumerate(members, 1):
            zf.extract(member, destination)
            if progress and (index == count or index % max(1, count // 25) == 0):
                progress("extract", current=index, total=count)


def effective_stage_root(stage):
    items = [p for p in Path(stage).iterdir() if p.name != "__MACOSX"]
    if len(items) == 1 and items[0].is_dir():
        return items[0]
    return Path(stage)


def validate_staged_app(stage_root):
    exe = Path(stage_root) / "PostalScanner.exe"
    if not exe.is_file():
        raise RuntimeError("새 패키지에 PostalScanner.exe가 없습니다. 기존 버전은 변경하지 않습니다.")
    if exe.stat().st_size < MIN_APP_EXE_BYTES:
        raise RuntimeError("새 PostalScanner.exe 파일이 비정상적으로 작습니다. 기존 버전은 변경하지 않습니다.")
    internal = Path(stage_root) / "_internal"
    if not internal.exists():
        raise RuntimeError("새 패키지의 _internal 폴더가 없습니다. 기존 버전은 변경하지 않습니다.")
    return exe


def _path_is_inside(child, parent):
    try:
        child = Path(child).resolve()
        parent = Path(parent).resolve()
        return os.path.commonpath([str(child), str(parent)]) == str(parent)
    except Exception:
        return False


def ensure_external_updater(target):
    executable = Path(sys.executable if getattr(sys, "frozen", False) else __file__).resolve()
    if _path_is_inside(executable, target):
        raise RuntimeError(
            "안전 업데이트 실행기가 설치 폴더 안에서 실행 중입니다. "
            "현재 버전은 변경하지 않습니다."
        )


def wait_for_pid_exit(pid, timeout=30.0, progress=None):
    pid = int(pid or 0)
    if pid <= 0:
        return
    if os.name == "nt":
        SYNCHRONIZE = 0x00100000
        handle = ctypes.windll.kernel32.OpenProcess(SYNCHRONIZE, False, pid)
        if handle:
            try:
                WAIT_OBJECT_0 = 0
                result = ctypes.windll.kernel32.WaitForSingleObject(handle, int(timeout * 1000))
                if result != WAIT_OBJECT_0:
                    raise RuntimeError("PostalScanner 종료를 기다리는 시간이 초과되었습니다. 기존 버전은 변경하지 않습니다.")
                return
            finally:
                ctypes.windll.kernel32.CloseHandle(handle)
        return

    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            os.kill(pid, 0)
        except OSError:
            return
        time.sleep(0.2)
    raise RuntimeError("PostalScanner 종료를 기다리는 시간이 초과되었습니다. 기존 버전은 변경하지 않습니다.")


def copy_preserved_data(old_dir, new_dir):
    old_dir, new_dir = Path(old_dir), Path(new_dir)
    for name in PRESERVE_NAMES:
        src = old_dir / name
        if not src.exists():
            continue
        dst = new_dir / name
        if src.is_dir():
            shutil.copytree(src, dst, dirs_exist_ok=True)
        else:
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)


def _safe_remove(path):
    path = Path(path)
    if not path.exists():
        return
    if path.is_dir():
        shutil.rmtree(path, ignore_errors=True)
    else:
        try:
            path.unlink()
        except FileNotFoundError:
            pass


def rollback_swap(target, backup, failed_dir=None):
    target, backup = Path(target), Path(backup)
    if target.exists():
        if failed_dir is None:
            failed_dir = target.parent / (target.name + "_UPDATE_FAILED")
        _safe_remove(failed_dir)
        try:
            target.rename(failed_dir)
        except Exception:
            _safe_remove(target)
    if backup.exists():
        backup.rename(target)


def run_update(args, report):
    target = Path(args.target_dir).resolve()
    ensure_external_updater(target)

    expected = str(args.sha256 or "").strip().lower()
    if len(expected) != 64 or any(c not in "0123456789abcdef" for c in expected):
        raise RuntimeError("SHA-256 값이 올바르지 않습니다.")

    restart_cmd = json.loads(args.restart_json)
    if not isinstance(restart_cmd, list) or not restart_cmd:
        raise RuntimeError("재시작 명령이 올바르지 않습니다.")

    parent = target.parent
    staging_container = parent / ("." + target.name + "_UPDATE_STAGING")
    package = parent / ("." + target.name + "_UPDATE_PACKAGE.zip")
    backup = parent / (target.name + "_UPDATE_BACKUP")
    previous_backup = parent / (target.name + "_UPDATE_BACKUP_PREVIOUS")
    failed_dir = parent / (target.name + "_UPDATE_FAILED")

    _safe_remove(staging_container)
    _safe_remove(package)
    _safe_remove(failed_dir)

    swapped = False
    old_backup_rotated = False
    try:
        report("status", stage="download")
        download_https(args.package_url, package, report)

        report("status", stage="verify")
        actual = sha256_file(package)
        if actual != expected:
            raise RuntimeError("업데이트 파일 SHA-256 검증에 실패했습니다. 기존 버전은 변경하지 않습니다.")

        report("status", stage="extract")
        safe_extract_zip(package, staging_container, report)
        stage_root = effective_stage_root(staging_container)
        validate_staged_app(stage_root)

        report("status", stage="waiting")
        wait_for_pid_exit(args.wait_pid, timeout=35.0, progress=report)

        report("status", stage="backup")
        if backup.exists():
            _safe_remove(previous_backup)
            backup.rename(previous_backup)
            old_backup_rotated = True

        target.rename(backup)
        swapped = True

        report("status", stage="install")
        stage_root.rename(target)
        copy_preserved_data(backup, target)
        validate_staged_app(target)

        report("status", stage="restart")
        proc = subprocess.Popen(restart_cmd, cwd=str(target))
        time.sleep(2.0)
        if proc.poll() is not None:
            raise RuntimeError("새 PostalScanner가 정상적으로 시작되지 않아 이전 버전으로 복구합니다.")

        if previous_backup.exists():
            _safe_remove(previous_backup)
        report("success")

    except Exception:
        if swapped and backup.exists():
            report("status", stage="rollback")
            rollback_swap(target, backup, failed_dir)
            if old_backup_rotated and previous_backup.exists() and not backup.exists():
                try:
                    previous_backup.rename(backup)
                except Exception:
                    pass
        raise
    finally:
        _safe_remove(package)
        _safe_remove(staging_container)


class ProgressWindow:
    STAGES = {
        "download": ("업데이트 파일 다운로드 중", 0),
        "verify": ("파일 무결성 검사 중", 72),
        "extract": ("새 버전 사전 검증 중", 80),
        "waiting": ("PostalScanner 안전 종료 확인 중", 86),
        "backup": ("현재 버전 보존 중", 90),
        "install": ("검증된 새 버전으로 교체 중", 95),
        "rollback": ("이전 버전으로 자동 복구 중", 96),
        "restart": ("새 PostalScanner 시작 확인 중", 99),
    }

    def __init__(self, args):
        self.args = args
        self.events = queue.Queue()
        self.failed = False
        self.root = tk.Tk()
        self.root.title("PostalScanner 업데이트")
        self.root.geometry("570x280")
        self.root.resizable(False, False)
        self.root.configure(bg="#172033")
        self.root.protocol("WM_DELETE_WINDOW", self._ignore_close)

        outer = tk.Frame(self.root, bg="#172033")
        outer.pack(fill="both", expand=True, padx=28, pady=24)
        tk.Label(outer, text="PostalScanner 안전 업데이트", font=("맑은 고딕", 16, "bold"), fg="white", bg="#172033").pack(anchor="w")
        self.status = tk.Label(outer, text="업데이트를 준비하고 있습니다...", font=("맑은 고딕", 11, "bold"), fg="#93c5fd", bg="#172033")
        self.status.pack(anchor="w", pady=(20, 8))
        self.progress = ttk.Progressbar(outer, orient="horizontal", mode="determinate", maximum=100, value=0)
        self.progress.pack(fill="x", ipady=5)
        row = tk.Frame(outer, bg="#172033")
        row.pack(fill="x", pady=(8, 0))
        self.detail = tk.Label(row, text="0 MB", font=("맑은 고딕", 9), fg="#cbd5e1", bg="#172033")
        self.detail.pack(side="left")
        self.percent = tk.Label(row, text="0%", font=("맑은 고딕", 10, "bold"), fg="white", bg="#172033")
        self.percent.pack(side="right")
        self.note = tk.Label(outer, text="검증이 끝나기 전에는 현재 프로그램을 변경하지 않습니다.", font=("맑은 고딕", 9), fg="#94a3b8", bg="#172033")
        self.note.pack(anchor="w", pady=(18, 0))
        self.close_button = tk.Button(outer, text="닫기", command=self.root.destroy, font=("맑은 고딕", 9, "bold"), state="disabled")
        self.close_button.pack(anchor="e", pady=(12, 0))

        self.root.after(40, self._poll)
        threading.Thread(target=self._worker, daemon=True).start()

    def _ignore_close(self):
        if self.failed:
            self.root.destroy()

    def report(self, kind, **payload):
        self.events.put((kind, payload))

    def _worker(self):
        try:
            run_update(self.args, self.report)
        except Exception as exc:
            self.report("error", message=str(exc))

    def _poll(self):
        try:
            while True:
                kind, payload = self.events.get_nowait()
                self._handle(kind, payload)
        except queue.Empty:
            pass
        try:
            if self.root.winfo_exists():
                self.root.after(40, self._poll)
        except tk.TclError:
            pass

    def _set_progress(self, value):
        value = max(0, min(100, int(value)))
        self.progress["value"] = value
        self.percent.config(text=f"{value}%")

    def _handle(self, kind, payload):
        if kind == "download":
            downloaded = int(payload.get("downloaded", 0) or 0)
            total = int(payload.get("total", 0) or 0)
            if total > 0:
                ratio = max(0.0, min(1.0, downloaded / float(total)))
                self._set_progress(int(ratio * 70.0))
                self.detail.config(text=f"다운로드 {ratio * 100:.0f}% · {_mb(downloaded):.1f} MB / {_mb(total):.1f} MB")
            else:
                self.detail.config(text=f"다운로드 중 · {_mb(downloaded):.1f} MB")
            self.status.config(text="업데이트 파일 다운로드 중")
            return

        if kind == "extract":
            current = int(payload.get("current", 0) or 0)
            total = max(1, int(payload.get("total", 1) or 1))
            local = current / float(total)
            self._set_progress(80 + int(local * 5))
            self.detail.config(text=f"압축 해제/검증 {local * 100:.0f}%")
            return

        if kind == "status":
            stage = str(payload.get("stage", ""))
            label, progress = self.STAGES.get(stage, ("업데이트 처리 중", int(self.progress["value"])))
            self.status.config(text=label)
            self._set_progress(progress)
            details = {
                "verify": "SHA-256 검증 중 · 아직 기존 프로그램 변경 없음",
                "waiting": "기존 PostalScanner 프로세스 종료 확인",
                "backup": "현재 설치 폴더를 통째로 백업",
                "install": "사전 검증 완료된 폴더를 적용",
                "rollback": "새 버전 제거 후 기존 폴더 원상복구",
                "restart": "새 실행파일 시작 여부 확인",
            }
            if stage in details:
                self.detail.config(text=details[stage])
            return

        if kind == "success":
            self.status.config(text="업데이트 완료", fg="#86efac")
            self.detail.config(text="새 PostalScanner가 정상적으로 시작되었습니다.")
            self._set_progress(100)
            self.note.config(text="이전 버전 백업은 복구용으로 유지됩니다.")
            self.root.after(1000, self.root.destroy)
            return

        if kind == "error":
            self.failed = True
            self.status.config(text="업데이트 실패", fg="#fca5a5")
            self.detail.config(text="기존 버전 유지/자동복구를 수행했습니다.")
            self.note.config(text="오류 내용을 확인해주세요. 자동 재시도는 하지 않습니다.")
            self.close_button.config(state="normal")
            messagebox.showerror("PostalScanner 업데이트 실패", "업데이트를 완료하지 못했습니다.\n\n" + str(payload.get("message", "")), parent=self.root)

    def run(self):
        self.root.mainloop()


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--target-dir", required=True)
    parser.add_argument("--package-url", required=True)
    parser.add_argument("--sha256", required=True)
    parser.add_argument("--restart-json", required=True)
    parser.add_argument("--wait-pid", required=True, type=int)
    return parser.parse_args()


def main():
    args = parse_args()
    ProgressWindow(args).run()


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        try:
            root = tk.Tk(); root.withdraw()
            messagebox.showerror("PostalScanner 업데이트 실패", "업데이트를 시작하지 못했습니다.\n\n" + str(e))
            root.destroy()
        except Exception:
            pass
        sys.exit(1)
