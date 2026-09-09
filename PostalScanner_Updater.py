# -*- coding: utf-8 -*-
"""
PostalScanner Updater

- HTTPS ZIP 다운로드
- 다운로드 진행률/용량 표시
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
import queue
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import zipfile
from pathlib import Path
from urllib.request import Request, urlopen

import tkinter as tk
from tkinter import ttk, messagebox

PRESERVE_NAMES = {
    "output",
    "audit",
    "metrics",
    "original",
    "openai_config.json",
    "openai_key.dat",
    "address_aliases.json",
    "clova_config.json",
    "update_config.json",
    "PostalScanner_Updater.py",
    "PostalScanner_Updater.exe",
}


def _mb(value):
    return float(value or 0) / (1024.0 * 1024.0)


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            chunk = f.read(1024 * 1024)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest().lower()


def download_https(url, destination, progress=None):
    if not str(url).lower().startswith("https://"):
        raise RuntimeError("HTTPS 업데이트만 허용됩니다.")

    req = Request(url, headers={"User-Agent": "PostalScanner-Updater/2.1.5"})
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
    with zipfile.ZipFile(zip_path, "r") as zf:
        members = zf.infolist()
        for member in members:
            target = (destination / member.filename).resolve()
            if os.path.commonpath([str(destination), str(target)]) != str(destination):
                raise RuntimeError("안전하지 않은 업데이트 ZIP 경로가 감지되었습니다.")

        count = max(1, len(members))
        for index, member in enumerate(members, 1):
            zf.extract(member, destination)
            if progress and (index == count or index % max(1, count // 20) == 0):
                progress("extract", current=index, total=count)


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


def run_update(args, report):
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

        report("status", stage="download")
        download_https(args.package_url, package, report)

        report("status", stage="verify")
        actual = sha256_file(package)
        if actual != expected:
            raise RuntimeError("업데이트 파일 SHA-256 검증에 실패했습니다.")

        report("status", stage="extract")
        safe_extract_zip(package, stage, report)
        stage_root = effective_stage_root(stage)

        report("status", stage="waiting")
        time.sleep(1.4)

        report("status", stage="backup")
        make_backup(target, backup)

        report("status", stage="install")
        try:
            clear_program_files(target)
            copy_tree_filtered(stage_root, target)
        except Exception:
            report("status", stage="rollback")
            restore_backup(target, backup)
            raise

    report("status", stage="restart")
    subprocess.Popen(restart_cmd, cwd=str(target))
    report("success")


class ProgressWindow:
    STAGES = {
        "download": ("업데이트 파일 다운로드 중", 0),
        "verify": ("파일 무결성 검사 중", 72),
        "extract": ("업데이트 파일 준비 중", 80),
        "waiting": ("PostalScanner 종료 확인 중", 86),
        "backup": ("기존 버전 백업 중", 90),
        "install": ("새 버전 설치 중", 95),
        "rollback": ("이전 버전으로 복구 중", 96),
        "restart": ("PostalScanner 재시작 중", 99),
    }

    def __init__(self, args):
        self.args = args
        self.events = queue.Queue()
        self.failed = False

        self.root = tk.Tk()
        self.root.title("PostalScanner 업데이트")
        self.root.geometry("560x270")
        self.root.resizable(False, False)
        self.root.configure(bg="#172033")
        self.root.protocol("WM_DELETE_WINDOW", self._ignore_close)

        outer = tk.Frame(self.root, bg="#172033")
        outer.pack(fill="both", expand=True, padx=28, pady=24)

        tk.Label(
            outer,
            text="PostalScanner 업데이트",
            font=("맑은 고딕", 16, "bold"),
            fg="white",
            bg="#172033",
        ).pack(anchor="w")

        self.status = tk.Label(
            outer,
            text="업데이트를 준비하고 있습니다...",
            font=("맑은 고딕", 11, "bold"),
            fg="#93c5fd",
            bg="#172033",
        )
        self.status.pack(anchor="w", pady=(20, 8))

        self.progress = ttk.Progressbar(
            outer,
            orient="horizontal",
            mode="determinate",
            maximum=100,
            value=0,
        )
        self.progress.pack(fill="x", ipady=5)

        row = tk.Frame(outer, bg="#172033")
        row.pack(fill="x", pady=(8, 0))

        self.detail = tk.Label(
            row,
            text="0 MB",
            font=("맑은 고딕", 9),
            fg="#cbd5e1",
            bg="#172033",
        )
        self.detail.pack(side="left")

        self.percent = tk.Label(
            row,
            text="0%",
            font=("맑은 고딕", 10, "bold"),
            fg="white",
            bg="#172033",
        )
        self.percent.pack(side="right")

        self.note = tk.Label(
            outer,
            text="업데이트가 완료되면 PostalScanner가 자동으로 다시 실행됩니다.",
            font=("맑은 고딕", 9),
            fg="#94a3b8",
            bg="#172033",
        )
        self.note.pack(anchor="w", pady=(18, 0))

        self.close_button = tk.Button(
            outer,
            text="닫기",
            command=self.root.destroy,
            font=("맑은 고딕", 9, "bold"),
            state="disabled",
        )
        self.close_button.pack(anchor="e", pady=(12, 0))

        self.root.after(60, self._poll)
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

        if self.root.winfo_exists():
            self.root.after(60, self._poll)

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
                overall = int(ratio * 70.0)
                self._set_progress(overall)
                self.detail.config(
                    text=f"다운로드 {ratio * 100:.0f}% · {_mb(downloaded):.1f} MB / {_mb(total):.1f} MB"
                )
            else:
                self.detail.config(text=f"다운로드 중 · {_mb(downloaded):.1f} MB")
            self.status.config(text="업데이트 파일 다운로드 중")
            return

        if kind == "extract":
            current = int(payload.get("current", 0) or 0)
            total = max(1, int(payload.get("total", 1) or 1))
            local = current / float(total)
            self._set_progress(80 + int(local * 5))
            self.detail.config(text=f"압축 해제 {local * 100:.0f}%")
            return

        if kind == "status":
            stage = str(payload.get("stage", ""))
            label, progress = self.STAGES.get(stage, ("업데이트 처리 중", int(self.progress["value"])))
            self.status.config(text=label)
            self._set_progress(progress)
            if stage == "verify":
                self.detail.config(text="SHA-256 검증 중")
            elif stage == "backup":
                self.detail.config(text="기존 프로그램 파일 안전 백업")
            elif stage == "install":
                self.detail.config(text="새 프로그램 파일 적용")
            elif stage == "rollback":
                self.detail.config(text="설치 실패 · 기존 버전 복구")
            elif stage == "restart":
                self.detail.config(text="설치 완료 · 프로그램 재실행")
            return

        if kind == "success":
            self.status.config(text="업데이트 완료", fg="#86efac")
            self.detail.config(text="PostalScanner를 다시 실행합니다.")
            self._set_progress(100)
            self.note.config(text="잠시 후 새 버전이 자동으로 실행됩니다.")
            self.root.after(1200, self.root.destroy)
            return

        if kind == "error":
            self.failed = True
            self.status.config(text="업데이트 실패", fg="#fca5a5")
            self.detail.config(text="기존 버전은 가능한 경우 자동 복구되었습니다.")
            self.note.config(text="오류 내용을 확인한 뒤 다시 시도해주세요.")
            self.close_button.config(state="normal")
            messagebox.showerror(
                "PostalScanner 업데이트 실패",
                "업데이트를 완료하지 못했습니다.\n\n" + str(payload.get("message", "")),
                parent=self.root,
            )

    def run(self):
        self.root.mainloop()


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--target-dir", required=True)
    parser.add_argument("--package-url", required=True)
    parser.add_argument("--sha256", required=True)
    parser.add_argument("--restart-json", required=True)
    return parser.parse_args()


def main():
    args = parse_args()
    ProgressWindow(args).run()


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        try:
            root = tk.Tk()
            root.withdraw()
            messagebox.showerror(
                "PostalScanner 업데이트 실패",
                "업데이트를 시작하지 못했습니다.\n\n" + str(e),
            )
            root.destroy()
        except Exception:
            pass
        sys.exit(1)
