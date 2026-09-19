"""Linux 原生文件对话框（Zenity / KDialog）。

Flet 的 FilePicker 在 Linux 上点击后从 Python 调用经常超时。
本辅助模块把对话框放到工作线程里运行。不要传 --modal（没有父窗口时会立即失败，看起来就像按钮卡死）。
"""



import asyncio
import os
import shutil
import subprocess
from pathlib import Path


class DialogUnavailable(RuntimeError):
    """本机没有可用对话框，或启动 zenity/kdialog 失败。"""


def _dialog_env() -> dict[str, str]:
    """复制环境变量，去掉可能让对话框无法弹出的 GDK/Qt 后端强制项。

    :return: 传给子进程的环境字典
    """
    env = os.environ.copy()
    env.pop("GDK_BACKEND", None)
    env.pop("QT_QPA_PLATFORM", None)
    return env


def zenity_available() -> bool:
    """是否存在 zenity 或 kdialog。

    :return: 至少有一个对话框工具则 True
    """
    return shutil.which("zenity") is not None or shutil.which("kdialog") is not None


def _run_sync(cmd: list[str], *, cwd: str | None = None) -> tuple[int, str, str]:
    """同步执行对话框命令。
    :param cmd: 命令及参数
    :param cwd: 工作目录
    :return: (退出码, stdout, stderr)
    :raises DialogUnavailable: 进程无法启动
    """
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
    """在工作线程中执行对话框，避免阻塞 UI 事件循环。
    :param cmd: 命令及参数
    :param cwd: 工作目录
    :return: (退出码, stdout, stderr)
    """
    return await asyncio.to_thread(_run_sync, cmd, cwd=cwd)


def _ok_or_cancel(code: int) -> bool:
    """工具正常运行时返回 True（确定或用户取消），False 表示崩溃。
    :param code: 进程退出码
    :return: 0/1 视为正常结束
    """
    return code in {0, 1}


def _looks_like_error(stderr: str) -> bool:
    """粗略判断 stderr 是否包含失败关键词。
    :param stderr: 标准错误输出
    :return: 疑似错误则为 True
    """
    text = stderr.lower()
    return any(token in text for token in ("error", "failed", "cannot", "unable"))


def _as_existing_dir(text: str) -> str | None:
    """把对话框输出整理成目录路径，必要时尝试创建。
    :param text: zenity/kdialog 打印的路径
    :return: 目录字符串；空输入为 None
    """
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
    """为文件夹对话框选择一个有效起始工作目录。
    :param initial_directory: 用户期望的起始路径
    :return: 已存在的目录，或 None
    """
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
    """返回选中的路径；取消时返回 []；无法启动对话框时返回 None。
    :param title: 对话框标题
    :param allow_multiple: 是否允许多选
    :param initial_directory: 起始目录
    :return: 已存在的文件路径列表、空列表或 None
    """
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
    """弹出文件夹选择框。
    :param title: 对话框标题
    :param initial_directory: 起始目录
    :return: 选中的目录；取消为 None
    :raises DialogUnavailable: 没有可用对话框工具
    """
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
    """弹出另存为对话框。
    :param title: 对话框标题
    :param default_name: 默认文件名
    :param initial_directory: 起始目录
    :return: 用户选择的路径；取消为 None
    :raises DialogUnavailable: 没有可用对话框工具
    """
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
