from __future__ import annotations

import atexit
import os
import signal
import subprocess
import sys
from pathlib import Path

_PID_FILE = Path.home() / ".config" / "markitdown-gui" / "float-ball.pid"


def _pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def stop_float_ball() -> None:
    if not _PID_FILE.exists():
        return
    try:
        pid = int(_PID_FILE.read_text(encoding="utf-8").strip())
    except ValueError:
        _PID_FILE.unlink(missing_ok=True)
        return
    if _pid_alive(pid):
        try:
            os.kill(pid, signal.SIGTERM)
        except OSError:
            pass
    _PID_FILE.unlink(missing_ok=True)


def ensure_float_ball(enabled: bool) -> None:
    if not enabled:
        stop_float_ball()
        return
    if _PID_FILE.exists():
        try:
            pid = int(_PID_FILE.read_text(encoding="utf-8").strip())
            if _pid_alive(pid):
                return
        except ValueError:
            pass
        _PID_FILE.unlink(missing_ok=True)

    _PID_FILE.parent.mkdir(parents=True, exist_ok=True)
    entry = Path(__file__).resolve().parents[2] / "float_ball_main.py"
    proc = subprocess.Popen(
        [sys.executable, str(entry)],
        start_new_session=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    _PID_FILE.write_text(str(proc.pid), encoding="utf-8")


atexit.register(stop_float_ball)
