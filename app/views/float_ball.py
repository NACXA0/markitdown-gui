"""独立悬浮球进程的启停。

开发环境：``python -m app.float_ball_app``。
打包 / AppImage：再拉起同一可执行文件，并设 ``MARKITDOWN_FLOAT_BALL=1``，
由 ``main.py`` 切到悬浮球界面（避免把 ``-m`` 参数交给 Flutter 客户端）。
"""

import os
import signal
import subprocess
import sys
from pathlib import Path

_PID_FILE = Path.home() / ".config" / "markitdown-gui" / "float-ball.pid"
_LOG_FILE = Path.home() / ".config" / "markitdown-gui" / "float-ball.log"
_ENV_FLAG = "MARKITDOWN_FLOAT_BALL"


def _pid_alive(pid: int) -> bool:
    """检测进程是否仍存在（不发送真实信号）。

    :param pid: 操作系统进程号
    :return: 进程存在则为 True
    """
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def stop_float_ball() -> None:
    """停止所有悬浮球进程（PID 文件 + 残留进程 + MD 窗口所属进程）。

    :return: None
    """
    pids: set[int] = set()
    if _PID_FILE.exists():
        try:
            pids.add(int(_PID_FILE.read_text(encoding="utf-8").strip()))
        except ValueError:
            pass
        _PID_FILE.unlink(missing_ok=True)
    try:
        out = subprocess.check_output(
            ["pgrep", "-f", "app.float_ball_app"], text=True, timeout=2
        )
        for line in out.split():
            try:
                pids.add(int(line.strip()))
            except ValueError:
                pass
    except (OSError, subprocess.SubprocessError):
        pass
    # 根据仍挂着的 MD 窗口 PID 清理孤儿 Flet 客户端
    try:
        tree = subprocess.check_output(
            ["xwininfo", "-root", "-tree"],
            text=True,
            timeout=2,
            env={**os.environ, "DISPLAY": os.environ.get("DISPLAY") or ":0"},
        )
        for line in tree.splitlines():
            if '"MD"' not in line:
                continue
            import re

            match = re.search(r"(0x[0-9a-fA-F]+)", line)
            if not match:
                continue
            try:
                prop = subprocess.check_output(
                    ["xprop", "-id", match.group(1), "_NET_WM_PID"],
                    text=True,
                    timeout=1,
                    env={**os.environ, "DISPLAY": os.environ.get("DISPLAY") or ":0"},
                )
            except (OSError, subprocess.SubprocessError):
                continue
            for part in prop.replace("=", " ").split():
                if part.isdigit():
                    pids.add(int(part))
                    break
    except (OSError, subprocess.SubprocessError):
        pass
    for pid in pids:
        if pid <= 1 or not _pid_alive(pid):
            continue
        try:
            os.kill(pid, signal.SIGTERM)
        except OSError:
            pass
    try:
        subprocess.run(
            ["pkill", "-f", "MARKITDOWN_FLOAT_BALL=1"],
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=2,
        )
    except (OSError, subprocess.SubprocessError):
        pass
    import time as _time

    _time.sleep(0.4)
    # 仍不退则强杀
    for pid in list(pids):
        if _pid_alive(pid):
            try:
                os.kill(pid, signal.SIGKILL)
            except OSError:
                pass
    _time.sleep(0.2)


def _is_python_launcher(executable: str) -> bool:
    """判断是否为普通 CPython 解释器（而非 Flet/Flutter 打包二进制）。

    :param executable: ``sys.executable`` 路径
    :return: 像 python/python3 则为 True
    """
    name = Path(executable).name.lower()
    return name.startswith("python")


def _launch_command() -> list[str]:
    """构造启动悬浮球的命令行。

    :return: ``Popen`` 用的 argv
    """
    if _is_python_launcher(sys.executable):
        return [sys.executable, "-m", "app.float_ball_app"]
    # AppImage：优先重入整个 AppImage，保证挂载与运行时完整
    appimage = (os.environ.get("APPIMAGE") or "").strip()
    if appimage and Path(appimage).is_file():
        return [appimage]
    return [sys.executable]


def _writable_cwd() -> Path:
    """返回可写工作目录（AppImage 的挂载点是只读的）。

    :return: 配置目录路径
    """
    path = Path.home() / ".config" / "markitdown-gui"
    path.mkdir(parents=True, exist_ok=True)
    return path


def ensure_float_ball(enabled: bool) -> None:
    """按开关启动或停止悬浮球窗口进程。

    :param enabled: True 则确保进程在跑；False 则停止
    :return: None
    """
    if not enabled:
        stop_float_ball()
        return

    # 先停掉全部残留，保证全局只有一个悬浮球
    stop_float_ball()

    cwd = _writable_cwd()
    env = os.environ.copy()
    # 去掉可能干扰二次启动的 Flet 内部变量
    for key in (
        "FLET_SERVER_UDS_PATH",
        "FLET_SERVER_PORT",
        "FLET_DART_BRIDGE_PORT",
    ):
        env.pop(key, None)

    cmd = _launch_command()
    if not _is_python_launcher(cmd[0]):
        env[_ENV_FLAG] = "1"
    if os.environ.get("APPIMAGE") or getattr(sys, "frozen", False):
        env["MARKITDOWN_DROPZONE"] = "1"

    # 悬浮球强制 X11：Wayland 下常出现超大黑底窗 + 无法贴边。
    if sys.platform.startswith("linux"):
        flag = (env.get("MARKITDOWN_FLOAT_BALL_WAYLAND") or "").strip().lower()
        if flag not in {"1", "true", "yes", "on"}:
            env["GDK_BACKEND"] = "x11"

    # AppImage 二次启动常继承 C/POSIX locale，mkdir 中文路径会炸；强制 UTF-8
    env.setdefault("PYTHONUTF8", "1")
    env.setdefault("PYTHONIOENCODING", "utf-8")
    for key, value in (
        ("LANG", "C.UTF-8"),
        ("LC_ALL", "C.UTF-8"),
        ("LC_CTYPE", "C.UTF-8"),
    ):
        current = env.get(key, "")
        if not current or "UTF-8" not in current.upper() and "utf8" not in current.lower():
            env[key] = value

    # 开发态需要项目根在 PYTHONPATH
    if _is_python_launcher(sys.executable):
        root = Path(__file__).resolve().parents[2]
        env["PYTHONPATH"] = str(root) + os.pathsep + env.get("PYTHONPATH", "")

    log = open(_LOG_FILE, "a", encoding="utf-8")  # noqa: SIM115
    try:
        log.write(f"\n--- launch cmd={cmd!r} cwd={cwd} ---\n")
        log.flush()
        proc = subprocess.Popen(
            cmd,
            cwd=str(cwd),
            env=env,
            start_new_session=True,
            stdout=log,
            stderr=subprocess.STDOUT,
        )
    except OSError as exc:
        log.write(f"launch failed: {exc}\n")
        log.close()
        raise
    _PID_FILE.write_text(str(proc.pid), encoding="utf-8")
