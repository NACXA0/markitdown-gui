"""Linux-native file dialogs via Zenity (reliable under Wayland).

Flet FilePicker on Linux shells out to Zenity/portal and often times out
when the desktop client is forced onto X11 or the service listener races.
"""

from __future__ import annotations

import asyncio
import shutil
from pathlib import Path


def zenity_available() -> bool:
    return shutil.which("zenity") is not None


async def pick_files(
    *,
    title: str = "选择文件",
    allow_multiple: bool = True,
    initial_directory: str | None = None,
) -> list[str]:
    if not zenity_available():
        return []
    cmd = [
        "zenity",
        "--file-selection",
        f"--title={title}",
    ]
    if allow_multiple:
        cmd.append("--multiple")
        cmd.append("--separator=\\n")
    if initial_directory:
        cmd.append(f"--filename={initial_directory.rstrip('/')}/")
    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await proc.communicate()
    except OSError:
        return []
    if proc.returncode != 0:
        return []
    text = stdout.decode("utf-8", errors="ignore").strip()
    if not text:
        return []
    paths = [p for p in text.split("\n") if p]
    return [p for p in paths if Path(p).exists()]


async def pick_directory(*, title: str = "选择文件夹") -> str | None:
    if not zenity_available():
        return None
    cmd = ["zenity", "--file-selection", "--directory", f"--title={title}"]
    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await proc.communicate()
    except OSError:
        return None
    if proc.returncode != 0:
        return None
    path = stdout.decode("utf-8", errors="ignore").strip()
    return path if path and Path(path).exists() else None
