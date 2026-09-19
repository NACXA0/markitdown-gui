"""Native file dialogs on Linux (Zenity / KDialog).

Flet FilePicker on Linux often times out if called from Python after the click.
This helper runs the dialog in a worker thread. Do not pass --modal (without a
parent window it can fail immediately and look like a dead button).
"""

from __future__ import annotations

import asyncio
import os
import shutil
import subprocess
from pathlib import Path


class DialogUnavailable(RuntimeError):
    pass


def _dialog_env() -> dict[str, str]:
    env = os.environ.copy()
    env.pop("GDK_BACKEND", None)
    env.pop("QT_QPA_PLATFORM", None)
    return env


def zenity_available() -> bool:
    return shutil.which("zenity") is not None or shutil.which("kdialog") is not None


def _run_sync(cmd: list[str], *, cwd: str | None = None) -> tuple[int, str, str]:
    try:
        proc = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=_dialog_env(),
            cwd=cwd,
            check=False,
        )
    except OSError as exc:
        raise DialogUnavailable(str(exc)) from exc
    return (
        proc.returncode,
        proc.stdout.decode("utf-8", errors="ignore").strip(),
        proc.stderr.decode("utf-8", errors="ignore").strip(),
    )


async def _run(cmd: list[str], *, cwd: str | None = None) -> tuple[int, str, str]:
    return await asyncio.to_thread(_run_sync, cmd, cwd=cwd)


def _ok_or_cancel(code: int) -> bool:
    """True if the tool ran (ok or user cancel). False means it crashed."""
    return code in {0, 1}


def _looks_like_error(stderr: str) -> bool:
    text = stderr.lower()
    return any(token in text for token in ("error", "failed", "cannot", "unable"))


def _as_existing_dir(text: str) -> str | None:
    raw = text.strip().removeprefix("file://")
    if not raw:
        return None
    path = Path(raw).expanduser()
    try:
        path.mkdir(parents=True, exist_ok=True)
    except OSError:
        pass
    return str(path)


def _start_cwd(initial_directory: str | None) -> str | None:
    if not initial_directory:
        return None
    path = Path(initial_directory).expanduser()
    if path.is_dir():
        return str(path)
    if path.parent.is_dir():
        return str(path.parent)
    return None


async def pick_files(
    *,
    title: str = "选择文件",
    allow_multiple: bool = True,
    initial_directory: str | None = None,
) -> list[str] | None:
    """Return selected paths, [] if cancelled, None if no dialog could start."""
    zenity = shutil.which("zenity")
    kdialog = shutil.which("kdialog")
    if zenity:
        cmd = ["zenity", "--file-selection", f"--title={title}"]
        if allow_multiple:
            cmd.extend(["--multiple", "--separator=|"])
        if initial_directory:
            cmd.append(f"--filename={initial_directory.rstrip('/')}/")
        try:
            code, text, stderr = await _run(cmd)
        except DialogUnavailable:
            pass
        else:
            if _ok_or_cancel(code) and not _looks_like_error(stderr):
                if code != 0 or not text:
                    return []
                paths = [p for p in text.replace("\n", "|").split("|") if p]
                return [p for p in paths if Path(p).exists()]
    if kdialog:
        start = (initial_directory or str(Path.home())).rstrip("/") + "/"
        cmd = ["kdialog", "--title", title, "--getopenfilename", start]
        if allow_multiple:
            cmd.append("--multiple")
        try:
            code, text, stderr = await _run(cmd)
        except DialogUnavailable:
            return None
        if not _ok_or_cancel(code) or _looks_like_error(stderr):
            return None
        if code != 0 or not text:
            return []
        parts = [p for p in text.replace("\n", " ").split("  ") if p]
        if len(parts) == 1:
            parts = [p for p in text.split("\n") if p]
        return [p.strip() for p in parts if Path(p.strip()).exists()]
    return None


async def pick_directory(
    *,
    title: str = "选择文件夹",
    initial_directory: str | None = None,
) -> str | None:
    zenity = shutil.which("zenity")
    kdialog = shutil.which("kdialog")
    start = _start_cwd(initial_directory)
    if zenity:
        cmd = ["zenity", "--file-selection", "--directory", f"--title={title}"]
        try:
            code, text, stderr = await _run(cmd, cwd=start)
        except DialogUnavailable:
            pass
        else:
            if _ok_or_cancel(code) and not _looks_like_error(stderr):
                if code != 0:
                    return None
                return _as_existing_dir(text)
            raise DialogUnavailable(stderr or "zenity directory picker failed")
    if kdialog:
        try:
            code, text, stderr = await _run(
                [
                    "kdialog",
                    "--title",
                    title,
                    "--getexistingdirectory",
                    start or str(Path.home()),
                ]
            )
        except DialogUnavailable as exc:
            raise DialogUnavailable(str(exc)) from exc
        if not _ok_or_cancel(code) or _looks_like_error(stderr):
            raise DialogUnavailable(stderr or "kdialog failed")
        if code != 0:
            return None
        return _as_existing_dir(text)
    raise DialogUnavailable("No file dialog (zenity/kdialog)")


async def save_file(
    *,
    title: str = "保存文件",
    default_name: str = "output.md",
    initial_directory: str | None = None,
) -> str | None:
    filename = default_name
    if initial_directory:
        filename = str(Path(initial_directory) / default_name)
    zenity = shutil.which("zenity")
    kdialog = shutil.which("kdialog")
    if zenity:
        cmd = [
            "zenity",
            "--file-selection",
            "--save",
            "--confirm-overwrite",
            f"--title={title}",
            f"--filename={filename}",
        ]
        try:
            code, text, stderr = await _run(cmd)
        except DialogUnavailable:
            pass
        else:
            if _ok_or_cancel(code) and not _looks_like_error(stderr):
                if code != 0:
                    return None
                return text or None
    if kdialog:
        code, text, stderr = await _run(
            ["kdialog", "--title", title, "--getsavefilename", filename]
        )
        if not _ok_or_cancel(code) or _looks_like_error(stderr):
            raise DialogUnavailable(stderr or "kdialog failed")
        if code != 0:
            return None
        return text or None
    raise DialogUnavailable("No file dialog (zenity/kdialog)")
