"""置顶悬浮卡片界面：单文件拖入转换，完成后复制 Markdown。

窗口与圆角矩形卡片等大、不透明；贴边时把窗口收成贴齐屏幕的窄条。
布局优先相对短边 / 物理毫米；像素仅用于窗口几何 API，并经屏幕探测换算。
"""

from __future__ import annotations

import asyncio
import json
import math
import os
import re
import subprocess
import sys
import time
from pathlib import Path

import flet as ft

from app import converter, linux_file_dialog
from app.i18n import t
from app.screen_layout import SPARK_N, BallLayout, detect_screen
from app.settings import load_settings, save_settings

MAGENTA = "#E2007A"
MAGENTA_SOFT = "#F7A0C9"
MAGENTA_DEEP = "#B80062"
WHITE = "#FFFFFF"
FACE = "#FFF8FB"
FACE_HOVER = "#FFE6F2"
YELLOW = "#FFD400"
BLACK = "#1A1A1A"
DANGER = "#E11D48"
MUTED = "#9B6B84"


def _tr(key: str, **kwargs: object) -> str:
    """按当前设置语言取文案（不触发导出目录创建副作用）。

    :param key: 文案键
    :param kwargs: 格式化参数
    :return: 翻译字符串
    """
    lang = "zh"
    try:
        path = Path.home() / ".config" / "markitdown-gui" / "settings.json"
        if path.is_file():
            data = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(data, dict) and isinstance(data.get("language"), str):
                lang = data["language"] or "zh"
    except (OSError, UnicodeError, json.JSONDecodeError, TypeError, ValueError):
        pass
    return t(lang, key, **kwargs)


def _use_native_dropzone() -> bool:
    """当前客户端是否带得上 flet_dropzone。

    官方轻量客户端（``python -m`` / ``uv run`` 拉起）没有该控件。
    仅打包产物、AppImage，或显式 ``MARKITDOWN_DROPZONE=1`` 时启用。

    :return: 应使用 Dropzone 则为 True
    """
    flag = os.environ.get("MARKITDOWN_DROPZONE", "").strip().lower()
    if flag in {"1", "true", "yes", "on"}:
        return True
    if flag in {"0", "false", "no", "off"}:
        return False
    if os.environ.get("APPIMAGE"):
        return True
    if getattr(sys, "frozen", False):
        return True
    # python 解释器走 ~/.flet 轻量客户端，不含 flet_dropzone 扩展
    name = Path(sys.executable).name.lower()
    return not name.startswith("python")


def _rotate_angle(value: object) -> float:
    """把 rotate 属性读成弧度。

    :param value: 数字或带 angle 的对象
    :return: 弧度
    """
    if value is None:
        return 0.0
    if isinstance(value, (int, float)):
        return float(value)
    return float(getattr(value, "angle", 0) or 0)


def _descendant_pids(root_pid: int) -> set[int]:
    """本进程及其全部子孙进程 PID。

    Flutter 桌面客户端常是 Flet 拉起的子进程，窗口挂在子进程上。

    :param root_pid: 根进程号
    :return: PID 集合
    """
    pids = {root_pid}
    try:
        out = subprocess.check_output(
            ["ps", "-eo", "pid=,ppid="], text=True, timeout=1.5
        )
    except (OSError, subprocess.SubprocessError):
        return pids
    children: dict[int, list[int]] = {}
    for line in out.splitlines():
        parts = line.split()
        if len(parts) < 2:
            continue
        try:
            pid, ppid = int(parts[0]), int(parts[1])
        except ValueError:
            continue
        children.setdefault(ppid, []).append(pid)
    stack = [root_pid]
    while stack:
        cur = stack.pop()
        for child in children.get(cur, ()):
            if child not in pids:
                pids.add(child)
                stack.append(child)
    return pids


def _x11_window_pid(wid: int) -> int | None:
    """读窗口 ``_NET_WM_PID``。

    :param wid: X11 窗口 id
    :return: PID 或 None
    """
    display = os.environ.get("DISPLAY") or ":0"
    try:
        out = subprocess.check_output(
            ["xprop", "-id", hex(wid), "_NET_WM_PID"],
            text=True,
            timeout=1,
            env={**os.environ, "DISPLAY": display},
        )
    except (OSError, subprocess.SubprocessError):
        return None
    for part in out.replace("=", " ").split():
        if part.isdigit():
            return int(part)
    return None


def _x11_md_window_ids() -> list[int]:
    """列出本悬浮窗相关的顶层 X11 窗口。

    优先：窗口 PID 属于本进程或其子孙；回退：标题 MD + Flet/MarkItDown class。

    :return: 窗口 id 列表（可能为空）
    """
    display = os.environ.get("DISPLAY") or ":0"
    env = {**os.environ, "DISPLAY": display}
    own = _descendant_pids(os.getpid())
    by_pid: list[int] = []
    by_title: list[int] = []

    # wmctrl -lp：一行列出 id / desktop / pid / host / title，比扫整棵树快
    try:
        out = subprocess.check_output(
            ["wmctrl", "-lp"], text=True, timeout=1.5, env=env
        )
        for line in out.splitlines():
            parts = line.split(None, 4)
            if len(parts) < 5:
                continue
            try:
                wid = int(parts[0], 16)
                pid = int(parts[2])
            except ValueError:
                continue
            title = parts[4]
            if pid in own:
                by_pid.append(wid)
            if title.strip() == "MD" or title.startswith("MD "):
                by_title.append(wid)
    except (OSError, subprocess.SubprocessError, FileNotFoundError):
        pass

    if by_pid or by_title:
        seen: set[int] = set()
        ids: list[int] = []
        for wid in by_pid + by_title:
            if wid not in seen:
                seen.add(wid)
                ids.append(wid)
        return ids

    # 回退：xwininfo 树里找标题 MD + class
    try:
        out = subprocess.check_output(
            ["xwininfo", "-root", "-tree"], text=True, timeout=1.5, env=env
        )
    except Exception:
        return []
    by_pid = []
    by_title = []
    seen: set[int] = set()
    for line in out.splitlines():
        if '"MD"' not in line:
            continue
        if not any(
            key in line.lower() for key in ("markitdown", "flet", "appveyor")
        ):
            continue
        match = re.search(r"(0x[0-9a-fA-F]+)", line)
        if not match:
            continue
        wid = int(match.group(1), 16)
        if wid in seen:
            continue
        seen.add(wid)
        pid = _x11_window_pid(wid)
        if pid is not None and pid in own:
            by_pid.append(wid)
        else:
            # 标题+class 已足够识别悬浮窗；外部工具进程没有父子关系时也能改几何
            by_title.append(wid)
    # 有本进程窗口时绝不要动残留僵尸窗，否则会改错尺寸/位置
    return by_pid if by_pid else by_title


def _x11_read_geometry(wid: int) -> tuple[int, int, int, int] | None:
    """用 xwininfo 读窗口绝对几何。

    :param wid: 窗口 id
    :return: (x, y, width, height) 或 None
    """
    display = os.environ.get("DISPLAY") or ":0"
    try:
        out = subprocess.check_output(
            ["xwininfo", "-id", hex(wid)],
            text=True,
            timeout=1,
            env={**os.environ, "DISPLAY": display},
        )
    except (OSError, subprocess.SubprocessError):
        return None
    vals: dict[str, int] = {}
    for key, pat in (
        ("x", r"Absolute upper-left X:\s*(-?\d+)"),
        ("y", r"Absolute upper-left Y:\s*(-?\d+)"),
        ("w", r"Width:\s*(\d+)"),
        ("h", r"Height:\s*(\d+)"),
    ):
        m = re.search(pat, out)
        if not m:
            return None
        vals[key] = int(m.group(1))
    return vals["x"], vals["y"], vals["w"], vals["h"]


def _x11_read_own_geometry() -> tuple[int, int, int, int] | None:
    """读本悬浮窗窗口真实几何（取列表中最后一个）。

    :return: (x, y, width, height) 或 None
    """
    ids = _x11_md_window_ids()
    if not ids:
        return None
    return _x11_read_geometry(ids[-1])


def _x11_bind(lib: object) -> None:
    """为 libX11 符号声明 64 位安全的 argtypes，避免 Display* 被截成 32 位后段错误。

    :param lib: ``ctypes.CDLL`` 实例
    :return: None
    """
    import ctypes

    disp = ctypes.c_void_p
    win = ctypes.c_ulong
    atom = ctypes.c_ulong
    status = ctypes.c_int
    lib.XOpenDisplay.argtypes = [ctypes.c_char_p]
    lib.XOpenDisplay.restype = disp
    lib.XCloseDisplay.argtypes = [disp]
    lib.XCloseDisplay.restype = status
    lib.XFlush.argtypes = [disp]
    lib.XFlush.restype = status
    lib.XSync.argtypes = [disp, ctypes.c_int]
    lib.XSync.restype = status
    lib.XDestroyWindow.argtypes = [disp, win]
    lib.XDestroyWindow.restype = status
    lib.XDefaultRootWindow.argtypes = [disp]
    lib.XDefaultRootWindow.restype = win
    lib.XInternAtom.argtypes = [disp, ctypes.c_char_p, ctypes.c_int]
    lib.XInternAtom.restype = atom
    lib.XChangeProperty.argtypes = [
        disp,
        win,
        atom,
        atom,
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_void_p,
        ctypes.c_int,
    ]
    lib.XChangeProperty.restype = status
    lib.XSendEvent.argtypes = [
        disp,
        win,
        ctypes.c_int,
        ctypes.c_long,
        ctypes.c_void_p,
    ]
    lib.XSendEvent.restype = status
    lib.XAllocSizeHints.argtypes = []
    lib.XAllocSizeHints.restype = ctypes.c_void_p
    lib.XSetWMNormalHints.argtypes = [disp, win, ctypes.c_void_p]
    lib.XSetWMNormalHints.restype = None
    lib.XMoveResizeWindow.argtypes = [
        disp,
        win,
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_uint,
        ctypes.c_uint,
    ]
    lib.XMoveResizeWindow.restype = status
    lib.XResizeWindow.argtypes = [disp, win, ctypes.c_uint, ctypes.c_uint]
    lib.XResizeWindow.restype = status
    lib.XDefaultScreen.argtypes = [disp]
    lib.XDefaultScreen.restype = ctypes.c_int
    lib.XRootWindow.argtypes = [disp, ctypes.c_int]
    lib.XRootWindow.restype = win
    lib.XCreatePixmap.argtypes = [
        disp,
        win,
        ctypes.c_uint,
        ctypes.c_uint,
        ctypes.c_uint,
    ]
    lib.XCreatePixmap.restype = ctypes.c_ulong
    lib.XFreePixmap.argtypes = [disp, ctypes.c_ulong]
    lib.XFreePixmap.restype = status
    lib.XCreateGC.argtypes = [disp, ctypes.c_ulong, ctypes.c_ulong, ctypes.c_void_p]
    lib.XCreateGC.restype = disp
    lib.XFreeGC.argtypes = [disp, disp]
    lib.XFreeGC.restype = status
    lib.XSetForeground.argtypes = [disp, disp, ctypes.c_ulong]
    lib.XSetForeground.restype = status
    lib.XFillRectangle.argtypes = [
        disp,
        ctypes.c_ulong,
        disp,
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_uint,
        ctypes.c_uint,
    ]
    lib.XFillRectangle.restype = status
    lib.XFillArc.argtypes = [
        disp,
        ctypes.c_ulong,
        disp,
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_uint,
        ctypes.c_uint,
        ctypes.c_int,
        ctypes.c_int,
    ]
    lib.XFillArc.restype = status


def _x11_load() -> object | None:
    """加载并绑定 libX11。

    :return: CDLL 或 None
    """
    try:
        import ctypes
        import ctypes.util
    except ImportError:
        return None
    name = ctypes.util.find_library("X11")
    if not name:
        return None
    lib = ctypes.cdll.LoadLibrary(name)
    _x11_bind(lib)
    return lib


def _x11_close_md_windows(*, keep_last: bool = False) -> None:
    """关闭残留的 MD 悬浮窗窗口，避免双开叠大黑底。

    :param keep_last: True 时保留列表中最后一个
    :return: None
    """
    if not sys.platform.startswith("linux"):
        return
    ids = _x11_md_window_ids()
    if keep_last and ids:
        ids = ids[:-1]
    if not ids:
        return
    # 优先用 WM 协议关掉，避免第二路 Display* 上硬 Destroy 与 GTK 抢窗口
    display_name = os.environ.get("DISPLAY") or ":0"
    env = {**os.environ, "DISPLAY": display_name}
    for wid in ids:
        try:
            subprocess.run(
                ["wmctrl", "-i", "-c", hex(wid)],
                check=False,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=1,
                env=env,
            )
        except (OSError, subprocess.SubprocessError, FileNotFoundError):
            pass
    # wmctrl 不可用时再走 XDestroyWindow（已声明 argtypes，避免指针截断）
    remaining = _x11_md_window_ids()
    if keep_last and remaining:
        remaining = remaining[:-1]
    if not remaining:
        return
    x11 = _x11_load()
    if x11 is None:
        return
    display = x11.XOpenDisplay(None)
    if not display:
        return
    try:
        for wid in remaining:
            x11.XDestroyWindow(display, wid)
        x11.XFlush(display)
    finally:
        x11.XCloseDisplay(display)


def _linux_force_geometry(
    width: int,
    height: int,
    left: int | None = None,
    top: int | None = None,
) -> bool:
    """先去装饰、取消最大化，再用 X11 强制窗口几何，并用 xwininfo 校验。

    不用 wmctrl 的退出码当作成功——它常打空或改不掉带标题栏的 GTK 窗。

    :param width: 目标宽
    :param height: 目标高
    :param left: 可选 X
    :param top: 可选 Y
    :return: 至少一个窗口尺寸已接近目标则为 True
    """
    if not sys.platform.startswith("linux"):
        return False
    ids = _x11_md_window_ids()
    if not ids:
        return False
    x11 = _x11_load()
    if x11 is None:
        return False
    import ctypes

    class XSizeHints(ctypes.Structure):
        _fields_ = [
            ("flags", ctypes.c_long),
            ("x", ctypes.c_int),
            ("y", ctypes.c_int),
            ("width", ctypes.c_int),
            ("height", ctypes.c_int),
            ("min_width", ctypes.c_int),
            ("min_height", ctypes.c_int),
            ("max_width", ctypes.c_int),
            ("max_height", ctypes.c_int),
            ("width_inc", ctypes.c_int),
            ("height_inc", ctypes.c_int),
            ("min_aspect_x", ctypes.c_int),
            ("min_aspect_y", ctypes.c_int),
            ("max_aspect_x", ctypes.c_int),
            ("max_aspect_y", ctypes.c_int),
            ("base_width", ctypes.c_int),
            ("base_height", ctypes.c_int),
            ("win_gravity", ctypes.c_int),
        ]

    class MotifWmHints(ctypes.Structure):
        _fields_ = [
            ("flags", ctypes.c_ulong),
            ("functions", ctypes.c_ulong),
            ("decorations", ctypes.c_ulong),
            ("input_mode", ctypes.c_long),
            ("status", ctypes.c_ulong),
        ]

    class XClientMessageEvent(ctypes.Structure):
        _fields_ = [
            ("type", ctypes.c_int),
            ("serial", ctypes.c_ulong),
            ("send_event", ctypes.c_int),
            ("display", ctypes.c_void_p),
            ("window", ctypes.c_ulong),
            ("message_type", ctypes.c_ulong),
            ("format", ctypes.c_int),
            ("data", ctypes.c_long * 5),
        ]

    class XEvent(ctypes.Union):
        _fields_ = [
            ("type", ctypes.c_int),
            ("xclient", XClientMessageEvent),
            ("pad", ctypes.c_long * 24),
        ]

    p_size = 1 << 3
    p_min = 1 << 4
    p_max = 1 << 5
    us_size = 1 << 1
    p_base = 1 << 8
    p_pos = 1 << 2
    us_pos = 1 << 0
    mwm_decorations = 1 << 1
    client_message = 33
    substructure_redirect = 1 << 20
    substructure_notify = 1 << 19
    prop_mode_replace = 0

    # XAllocSizeHints 返回 XSizeHints*；上面 restype 是 c_void_p，再转 POINTER
    x11.XAllocSizeHints.restype = ctypes.POINTER(XSizeHints)
    display = x11.XOpenDisplay(None)
    if not display:
        return False
    touched = False
    try:
        root = x11.XDefaultRootWindow(display)
        net_state = x11.XInternAtom(display, b"_NET_WM_STATE", False)
        max_h = x11.XInternAtom(display, b"_NET_WM_STATE_MAXIMIZED_HORZ", False)
        max_v = x11.XInternAtom(display, b"_NET_WM_STATE_MAXIMIZED_VERT", False)
        net_fs = x11.XInternAtom(display, b"_NET_WM_STATE_FULLSCREEN", False)
        motif = x11.XInternAtom(display, b"_MOTIF_WM_HINTS", False)
        for wid in ids:
            # Motif：去掉标题栏/边框，否则 WM 拒绝缩到球大小
            mwm = MotifWmHints()
            mwm.flags = mwm_decorations
            mwm.decorations = 0
            x11.XChangeProperty(
                display,
                wid,
                motif,
                motif,
                32,
                prop_mode_replace,
                ctypes.byref(mwm),
                5,
            )
            for atom in (max_h, max_v, net_fs):
                ev = XEvent()
                ev.xclient.type = client_message
                ev.xclient.serial = 0
                ev.xclient.send_event = 1
                ev.xclient.display = display
                ev.xclient.window = wid
                ev.xclient.message_type = net_state
                ev.xclient.format = 32
                ev.xclient.data[0] = 0  # _NET_WM_STATE_REMOVE
                ev.xclient.data[1] = atom
                ev.xclient.data[2] = 0
                ev.xclient.data[3] = 1
                ev.xclient.data[4] = 0
                x11.XSendEvent(
                    display,
                    root,
                    False,
                    substructure_redirect | substructure_notify,
                    ctypes.byref(ev),
                )
            hints = x11.XAllocSizeHints()
            if not hints:
                continue
            flags = p_size | p_min | p_max | us_size | p_base
            hints.contents.width = width
            hints.contents.height = height
            hints.contents.min_width = width
            hints.contents.min_height = height
            hints.contents.max_width = width
            hints.contents.max_height = height
            hints.contents.base_width = width
            hints.contents.base_height = height
            if left is not None and top is not None:
                flags |= p_pos | us_pos
                hints.contents.x = int(left)
                hints.contents.y = int(top)
                hints.contents.flags = flags
                x11.XSetWMNormalHints(display, wid, hints)
                x11.XMoveResizeWindow(
                    display,
                    wid,
                    int(left),
                    int(top),
                    width,
                    height,
                )
            else:
                hints.contents.flags = flags
                x11.XSetWMNormalHints(display, wid, hints)
                x11.XResizeWindow(
                    display,
                    wid,
                    width,
                    height,
                )
            touched = True
        x11.XFlush(display)
        x11.XSync(display, False)
    finally:
        x11.XCloseDisplay(display)

    if not touched:
        return False
    # 读回校验：给合成器一瞬时间；允许少量误差
    time.sleep(0.05)
    geo = _x11_read_geometry(ids[-1])
    if geo is None:
        return False
    _, _, rw, rh = geo
    return abs(rw - width) <= 8 and abs(rh - height) <= 8


def _linux_apply_shape(
    width: int,
    height: int,
    ball_left: float,
    ball_top: float,
    ball: float,
    copy_rect: tuple[float, float, float, float] | None,
    *,
    clip_side: str | None = None,
    visible_inset: float | None = None,
) -> bool:
    """用 XShape 裁可见区（圆/月牙），输入区保持整窗矩形以便拖放。

    Bounding=可见外形；Input=整窗，避免 Dropzone 收不到投放。

    :param width: 窗口宽
    :param height: 窗口高
    :param ball_left: 圆左侧
    :param ball_top: 圆顶侧
    :param ball: 球径（含旋风环）
    :param copy_rect: 可选 (left, top, w, h)
    :param clip_side: 贴边方向；与 visible_inset 一起裁成月牙
    :param visible_inset: 贴边时露出的宽度；None 表示整圆
    :return: 成功则为 True
    """
    if not sys.platform.startswith("linux"):
        return False
    ids = _x11_md_window_ids()
    if not ids:
        return False
    try:
        import ctypes
        import ctypes.util
    except ImportError:
        return False
    x11 = _x11_load()
    lib_ext = ctypes.util.find_library("Xext")
    if x11 is None or not lib_ext:
        return False

    shape_bounding = 0
    shape_input = 1
    shape_set = 0

    xext = ctypes.cdll.LoadLibrary(lib_ext)
    xext.XShapeCombineMask.argtypes = [
        ctypes.c_void_p,
        ctypes.c_ulong,
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_ulong,
        ctypes.c_int,
    ]
    xext.XShapeCombineMask.restype = None
    display = x11.XOpenDisplay(None)
    if not display:
        return False
    ok = False
    try:
        screen = x11.XDefaultScreen(display)
        root = x11.XRootWindow(display, screen)
        w = max(1, int(width))
        h = max(1, int(height))
        bound = x11.XCreatePixmap(display, root, w, h, 1)
        full = x11.XCreatePixmap(display, root, w, h, 1)
        if not bound or not full:
            if bound:
                x11.XFreePixmap(display, bound)
            if full:
                x11.XFreePixmap(display, full)
            return False
        gc = x11.XCreateGC(display, bound, 0, None)
        if not gc:
            x11.XFreePixmap(display, bound)
            x11.XFreePixmap(display, full)
            return False
        # —— Bounding：圆 / 月牙 + 可选复制键 ——
        x11.XSetForeground(display, gc, 0)
        x11.XFillRectangle(display, bound, gc, 0, 0, w, h)
        x11.XSetForeground(display, gc, 1)
        bx = int(round(ball_left))
        by = int(round(ball_top))
        bd = max(1, int(round(ball)))
        x11.XFillArc(display, bound, gc, bx, by, bd, bd, 0, 360 * 64)
        if (
            clip_side
            and visible_inset is not None
            and visible_inset < bd
        ):
            inset = max(1, int(round(visible_inset)))
            x11.XSetForeground(display, gc, 0)
            if clip_side == "right":
                # 向右藏：只留圆的左侧（靠屏幕内侧）
                x11.XFillRectangle(
                    display, bound, gc, bx + inset, 0, max(1, w - bx - inset), h
                )
            elif clip_side == "left":
                x11.XFillRectangle(display, bound, gc, 0, 0, max(1, bx + bd - inset), h)
            elif clip_side == "bottom":
                x11.XFillRectangle(
                    display, bound, gc, 0, by + inset, w, max(1, h - by - inset)
                )
            elif clip_side == "top":
                x11.XFillRectangle(display, bound, gc, 0, 0, w, max(1, by + bd - inset))
            x11.XSetForeground(display, gc, 1)
        if copy_rect is not None:
            cl, ct, cw, ch = copy_rect
            if cw > 1 and ch > 1:
                x11.XFillRectangle(
                    display,
                    bound,
                    gc,
                    int(round(cl)),
                    int(round(ct)),
                    max(1, int(round(cw))),
                    max(1, int(round(ch))),
                )
        # —— Input：整窗矩形，保证文件拖放命中 ——
        x11.XSetForeground(display, gc, 1)
        x11.XFillRectangle(display, full, gc, 0, 0, w, h)
        for wid in ids:
            xext.XShapeCombineMask(
                display,
                wid,
                shape_bounding,
                0,
                0,
                bound,
                shape_set,
            )
            xext.XShapeCombineMask(
                display,
                wid,
                shape_input,
                0,
                0,
                full,
                shape_set,
            )
            ok = True
        x11.XFreeGC(display, gc)
        x11.XFreePixmap(display, bound)
        x11.XFreePixmap(display, full)
        x11.XFlush(display)
    finally:
        x11.XCloseDisplay(display)
    return ok


class FloatBallApp:
    """悬浮窗窗口控制器。"""

    def __init__(self, page: ft.Page) -> None:
        """构建不透明圆角矩形置顶小窗并绑定拖放 / 转换 / 复制。

        :param page: Flet 页面
        :return: None
        """
        self.page = page
        self._phase = "empty"
        self._path: str | None = None
        self._markdown: str | None = None
        self._error: str | None = None
        self._dock_side: str | None = None
        self._reveal = "open"
        self._hover_delete = False
        self._token = 0
        self._applying_dock = False
        self._pulse_gen = 0
        self._copy_pulse = False
        self._warn_until = 0.0
        self._spinning = False
        self.screen = detect_screen()
        self.m = BallLayout.from_screen(self.screen)
        self._screen = (self.screen.width, self.screen.height)
        self._anchor_left = 0.0
        self._anchor_top = 0.0
        self._hide_gen = 0
        self._expand_gen = 0
        self._move_gen = 0
        self._breath_gen = 0
        self._ignore_move_until = 0.0
        self._ignore_hover_until = 0.0
        self._user_dragging = False
        self._file_dnd = False  # 系统文件拖入中：禁止当成窗口拖动去贴边
        self._internal_copy = False  # 屏缘放不下时，复制键画在卡内
        self._pointer_over = False
        self._chrome_hover = False
        self._frame_pad = 0.0
        self._dropzone: ft.Control | None = None

        # 启动前清掉上次残留的 MD 僵尸窗，避免几何打到错误目标
        _x11_close_md_windows(keep_last=False)

        self._configure_window()
        self.clipboard = ft.Clipboard()
        self.file_picker = ft.FilePicker()
        page.services.extend([self.clipboard, self.file_picker])
        page.window.on_event = self._on_window_event

        self._build_controls()
        self._restore_position()
        self._sync_visuals()
        root = self._wrap_dropzone(self.host)
        page.add(root)
        page.update()
        self.page.run_task(self._boot_spin)

    def _configure_window(self) -> None:
        """设置无边框置顶不透明小窗，尺寸等于卡片。

        先隐藏再设尺寸，避免首帧出现超大窗。

        :return: None
        """
        page = self.page
        page.title = "MD"
        page.padding = 0
        page.spacing = 0
        page.horizontal_alignment = ft.CrossAxisAlignment.START
        page.vertical_alignment = ft.MainAxisAlignment.START
        page.theme_mode = ft.ThemeMode.LIGHT
        # 窗体铺品红，避免圆角外露出白角
        solid = ft.Theme(
            scaffold_bgcolor=MAGENTA,
            canvas_color=MAGENTA,
        )
        page.theme = solid
        page.dark_theme = solid
        page.bgcolor = MAGENTA
        win = page.window
        win.visible = False
        fw, fh = self._open_frame_size()
        win.width = fw
        win.height = fh
        win.min_width = fw
        win.min_height = fh
        win.max_width = fw
        win.max_height = fh
        win.always_on_top = True
        win.frameless = True
        win.bgcolor = MAGENTA
        win.opacity = 1
        win.resizable = False
        win.maximizable = False
        win.minimizable = False
        win.maximized = False
        win.full_screen = False
        win.title_bar_hidden = True
        win.title_bar_buttons_hidden = True
        win.skip_task_bar = True

    def _build_controls(self) -> None:
        """组装品红外框 + 内白圆角面、旋风、复制键与礼花。

        :return: None
        """
        ease = ft.Animation(280, ft.AnimationCurve.EASE_OUT_CUBIC)
        pop = ft.Animation(360, ft.AnimationCurve.EASE_OUT_BACK)
        fade = ft.Animation(220, ft.AnimationCurve.EASE_OUT)
        soft = ft.Animation(640, ft.AnimationCurve.EASE_IN_OUT)
        m = self.m
        cw, ch = m.card_w, m.card_h
        frame = m.border
        inner_w = max(m.u(2), cw - frame * 2)
        inner_h = max(m.u(2), ch - frame * 2)

        self.hint_icon = ft.Icon(
            ft.Icons.CLOUD_UPLOAD_ROUNDED, size=m.icon, color=MAGENTA
        )
        self.hint_text = ft.Text(
            _tr("float_drop_hint"),
            size=m.text_sm,
            weight=ft.FontWeight.W_600,
            color=MUTED,
            text_align=ft.TextAlign.CENTER,
            width=inner_w,
            no_wrap=True,
        )
        self.file_icon = ft.Icon(
            ft.Icons.DESCRIPTION_ROUNDED, size=m.icon, color=MAGENTA
        )
        self.x_icon = ft.Icon(ft.Icons.CLOSE_ROUNDED, size=m.x_icon, color=DANGER)
        self.ok_text = ft.Text(
            _tr("float_copy_ok"),
            size=m.text_sm,
            weight=ft.FontWeight.W_700,
            color=MAGENTA_DEEP,
            text_align=ft.TextAlign.CENTER,
            width=inner_w,
            no_wrap=True,
        )
        # 图标放进固定方槽，避免 Material 图标视觉重心偏一侧
        self.hint_icon_slot = ft.Container(
            content=self.hint_icon,
            width=m.icon,
            height=m.icon,
            alignment=ft.Alignment.CENTER,
            scale=1,
            animate_scale=soft,
            animate_opacity=soft,
        )
        hint_col = ft.Column(
            [self.hint_icon_slot, self.hint_text],
            spacing=m.u(0.55),
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            alignment=ft.MainAxisAlignment.CENTER,
            tight=True,
        )
        self.hint_box = self._layer(hint_col, 1)
        self.file_box = self._layer(
            ft.Container(
                content=self.file_icon,
                width=m.icon,
                height=m.icon,
                alignment=ft.Alignment.CENTER,
            ),
            0,
        )
        self.x_box = self._layer(
            ft.Container(
                content=self.x_icon,
                width=m.x_icon,
                height=m.x_icon,
                alignment=ft.Alignment.CENTER,
            ),
            0,
        )
        self.ok_box = self._layer(self.ok_text, 0)

        self.core = ft.Container(
            content=ft.Stack(
                [self.hint_box, self.file_box, self.x_box, self.ok_box],
                width=inner_w,
                height=inner_h,
                alignment=ft.Alignment.CENTER,
            ),
            width=inner_w,
            height=inner_h,
            bgcolor=FACE,
            alignment=ft.Alignment.CENTER,
            animate_opacity=fade,
        )
        self.ball_hit = ft.GestureDetector(
            content=self.core,
            on_enter=self._on_ball_enter,
            on_exit=self._on_ball_exit,
            on_tap=self._on_ball_tap,
            on_pan_start=self._on_ball_pan,
            mouse_cursor=ft.MouseCursor.BASIC,
        )
        self.ball_slot = ft.Container(
            content=self.ball_hit,
            width=inner_w,
            height=inner_h,
            left=0,
            top=0,
            animate_position=ease,
        )

        ring_left = (inner_w - m.ring) / 2
        ring_top = (inner_h - m.ring) / 2
        # 旋风：黄黑甜甜圈（与初版设计一致）
        spin_hole = max(m.u(2.2), m.ring * 0.58)
        self.spin = ft.Container(
            width=m.ring,
            height=m.ring,
            border_radius=m.ring / 2,
            gradient=ft.SweepGradient(
                colors=[YELLOW, BLACK, YELLOW, BLACK, YELLOW],
                stops=[0.0, 0.25, 0.5, 0.75, 1.0],
            ),
            content=ft.Container(
                width=spin_hole,
                height=spin_hole,
                border_radius=spin_hole / 2,
                bgcolor=FACE,
                alignment=ft.Alignment.CENTER,
            ),
            alignment=ft.Alignment.CENTER,
            rotate=0,
            opacity=0,
            animate_opacity=fade,
            animate_rotation=ft.Animation(900, ft.AnimationCurve.LINEAR),
            ignore_interactions=True,
        )
        self.spin_slot = ft.Container(
            content=self.spin,
            width=m.ring,
            height=m.ring,
            left=ring_left,
            top=ring_top,
            animate_position=ease,
            ignore_interactions=True,
        )

        self.copy_label = ft.Text(
            _tr("copy_clipboard"),
            size=m.text_md,
            weight=ft.FontWeight.W_700,
            color=WHITE,
            text_align=ft.TextAlign.CENTER,
        )
        # 圆角矩形（非胶囊）：从方卡下方「弹出」
        copy_radius = max(m.u(0.55), m.copy_h * 0.28)
        self.copy_box = ft.Container(
            content=self.copy_label,
            alignment=ft.Alignment.CENTER,
            bgcolor=MAGENTA,
            border=ft.Border.all(max(1.0, m.u(0.22)), MAGENTA_DEEP),
            border_radius=copy_radius,
            width=0,
            height=0,
            opacity=0,
            scale=0.55,
            clip_behavior=ft.ClipBehavior.HARD_EDGE,
            animate_opacity=fade,
            animate_scale=pop,
            animate_size=ease,
            animate_position=ease,
            on_click=self._on_copy,
            left=(cw - m.copy_w) / 2,
            top=ch + m.gap,
        )

        self.sparks: list[ft.Container] = []
        spark_colors = [
            MAGENTA,
            YELLOW,
            WHITE,
            MAGENTA_SOFT,
            DANGER,
            MAGENTA_DEEP,
            YELLOW,
            WHITE,
            YELLOW,
            MAGENTA,
            DANGER,
            MAGENTA_SOFT,
        ]
        for i in range(SPARK_N):
            spark = ft.Container(
                width=m.spark_dot,
                height=m.spark_dot,
                bgcolor=spark_colors[i % len(spark_colors)],
                border_radius=m.spark_dot / 2,
                opacity=0,
                scale=0.2,
                left=inner_w / 2,
                top=inner_h / 2,
                animate_opacity=ft.Animation(420, ft.AnimationCurve.EASE_OUT),
                animate_position=ft.Animation(480, ft.AnimationCurve.EASE_OUT_CUBIC),
                animate_scale=ft.Animation(420, ft.AnimationCurve.EASE_OUT),
                ignore_interactions=True,
            )
            self.sparks.append(spark)

        # 白底圆角内容面（是 face_shell 的 content，不能设 left/top/expand）
        self.face = ft.Container(
            content=ft.Stack(
                [
                    self.spin_slot,
                    self.ball_slot,
                ],
                width=inner_w,
                height=inner_h,
                clip_behavior=ft.ClipBehavior.HARD_EDGE,
                alignment=ft.Alignment.CENTER,
            ),
            width=inner_w,
            height=inner_h,
            bgcolor=FACE,
            border=ft.Border.all(max(1.0, m.u(0.22)), MAGENTA_SOFT),
            border_radius=m.radius,
            clip_behavior=ft.ClipBehavior.HARD_EDGE,
            animate=soft,
        )
        # 品红外壳只包住方卡，复制键在壳外下方弹出，不把整窗拉成大长方形壳
        self.face_shell = ft.Container(
            content=self.face,
            width=cw,
            height=ch,
            left=0,
            top=0,
            bgcolor=MAGENTA,
            padding=frame,
            border_radius=0,
            clip_behavior=ft.ClipBehavior.HARD_EDGE,
            animate_position=ease,
            animate=soft,
        )
        self.fx_layer = ft.Stack(
            self.sparks,
            width=cw,
            height=ch,
            left=0,
            top=0,
            clip_behavior=ft.ClipBehavior.NONE,
        )
        self.stack = ft.Stack(
            [self.face_shell, self.copy_box, self.fx_layer],
            width=cw,
            height=ch,
            clip_behavior=ft.ClipBehavior.NONE,
        )
        # 宿主：扩展区底色与品红一致，让复制键像从卡片「长」出来
        self.card = ft.Container(
            content=self.stack,
            width=cw,
            height=ch,
            bgcolor=MAGENTA,
            padding=0,
            border_radius=0,
            clip_behavior=ft.ClipBehavior.NONE,
            alignment=ft.Alignment.TOP_CENTER,
            animate=soft,
        )
        self.host = ft.GestureDetector(
            content=self.card,
            on_enter=self._on_host_enter,
            on_exit=self._on_host_exit,
            width=cw,
            height=ch,
        )
        self._frame_pad = frame

    def _layer(self, inner: ft.Control, opacity: float) -> ft.Container:
        """卡片内一层可淡入淡出的内容。

        :param inner: 文案或图标
        :param opacity: 初始透明度
        :return: 铺满内容区的容器
        """
        return ft.Container(
            content=inner,
            alignment=ft.Alignment.CENTER,
            width=self.m.card_w,
            height=self.m.card_h,
            # 不加水平 padding：窄窗裁切时 padding 会让文案看起来偏一侧
            padding=0,
            opacity=opacity,
            scale=1 if opacity else 0.85,
            animate_opacity=180,
            animate_scale=220,
            ignore_interactions=True,
        )

    def _wrap_dropzone(self, content: ft.Control) -> ft.Control:
        """在支持原生拖放的客户端外包一层 Dropzone。

        :param content: 悬浮窗根控件
        :return: Dropzone 或原控件
        """
        if not _use_native_dropzone():
            return content
        try:
            import flet_dropzone as ftd
        except ImportError:
            return content

        fw, fh = self._frame_size()
        zone = ftd.Dropzone(
            content=content,
            width=fw,
            height=fh,
            on_dropped=self._on_dropped,
            on_entered=self._on_drag_entered,
            on_exited=self._on_drag_exited,
        )
        self._dropzone = zone
        return zone

    @staticmethod
    def _normalize_drop_path(raw: object) -> str | None:
        """把拖放路径整理成本地绝对路径。

        :param raw: Dropzone 给出的 path
        :return: 可用路径或 None
        """
        path = str(raw or "").strip()
        if not path or path.startswith("blob:"):
            return None
        if path.startswith("file:"):
            from urllib.parse import unquote, urlparse

            parsed = urlparse(path)
            path = unquote(parsed.path or "")
        if path.startswith("/") and path != "/":
            return path
        return None

    async def _on_dropped(self, e: object) -> None:
        """接收拖放路径。

        :param e: Dropzone 事件
        :return: None
        """
        files = getattr(e, "files", None) or []
        paths: list[str] = []
        for file in files:
            path = self._normalize_drop_path(getattr(file, "path", None))
            if path:
                paths.append(path)
        # 无论是否收下文件，都结束文件拖放态，并清掉误触的窗口拖动标记
        self._file_dnd = False
        self._user_dragging = False
        self._move_gen += 1
        self._ignore_move_until = time.monotonic() + 3.0
        if paths:
            self._hide_gen += 1
            self._expand_gen += 1
            self._pointer_over = True
            if self._dock_side and self._reveal != "open":
                self._set_reveal("open", move=True)
            self._accept_paths(paths)

    def _restore_position(self) -> None:
        """恢复上次坐标；缺省贴在屏幕右侧中部。

        仅贴边时收成窄条；窗口始终留在屏内贴齐该边。

        :return: None
        """
        settings = load_settings()
        sw, sh = self._screen
        ow, oh = self._open_frame_size()
        top = (sh - oh) / 2
        if settings.float_ball_y is not None:
            top = settings.float_ball_y
        top = max(0, min(top, max(0, sh - oh)))
        if settings.float_ball_x is not None:
            left = settings.float_ball_x
        else:
            left = sw - ow
        left = max(0, min(left, max(0, sw - ow)))
        self._anchor_left = left
        self._anchor_top = top
        self._apply_dock_from_pos(left, top, snap_window=False)
        # 冷启动先展开方卡，避免贴边窄条几乎看不见、被当成没启动
        if self._dock_side:
            self._reveal = "open"
        self._move_window_to_reveal()

    def _near_left(self, left: float) -> bool:
        """窗口是否贴着屏幕左缘。"""
        return left <= self.m.edge

    def _near_right(self, left: float, width: float | None = None) -> bool:
        """窗口是否贴着屏幕右缘。"""
        sw, _ = self._screen
        fw = self._frame_size()[0] if width is None else width
        return left + fw >= sw - self.m.edge

    def _near_top(self, top: float) -> bool:
        """窗口是否贴着屏幕上缘。"""
        return top <= self.m.edge

    def _near_bottom(self, top: float, height: float | None = None) -> bool:
        """窗口是否贴着屏幕下缘。"""
        _, sh = self._screen
        fh = self._frame_size()[1] if height is None else height
        return top + fh >= sh - self.m.edge

    def _edge_distances(
        self, left: float, top: float, width: float, height: float
    ) -> dict[str, float]:
        """窗口四边到屏幕对应边的距离。

        :return: left/right/top/bottom → 距离
        """
        sw, sh = self._screen
        return {
            "left": left,
            "right": sw - (left + width),
            "top": top,
            "bottom": sh - (top + height),
        }

    def _pick_dock_side(
        self, left: float, top: float, width: float, height: float
    ) -> str | None:
        """取最近且小于 edge 的一边；都不贴则自由悬浮。

        :return: 边名或 None
        """
        dists = self._edge_distances(left, top, width, height)
        side, dist = min(dists.items(), key=lambda item: item[1])
        if dist <= self.m.edge:
            return side
        return None

    def _hide_inset(self) -> float:
        """半藏条厚度。"""
        return self.m.hide_strip

    def _window_target_pos(self) -> tuple[float, float]:
        """按贴边方向计算窗口左上角（始终留在屏内贴齐该边）。

        半隐藏靠缩小窗口成窄条，不再推出屏幕。
        未贴边时返回锚点。

        :return: (left, top)
        """
        sw, sh = self._screen
        ww, wh = self._frame_size()
        ax, ay = self._anchor_left, self._anchor_top
        if not self._dock_side:
            return ax, ay
        if self._dock_side == "left":
            return 0.0, ay
        if self._dock_side == "right":
            return max(0.0, sw - ww), ay
        if self._dock_side == "top":
            return ax, 0.0
        if self._dock_side == "bottom":
            return ax, max(0.0, sh - wh)
        return ax, ay

    def _begin_programmatic_move(self) -> None:
        """标记程序化移窗，短暂忽略随后的 MOVED / 进出事件。"""
        self._applying_dock = True
        now = time.monotonic()
        self._ignore_move_until = now + 0.45
        self._ignore_hover_until = now + 0.2

    def _end_programmatic_move(self) -> None:
        """结束程序化移窗标记。"""
        self._applying_dock = False

    def _hover_blocked(self) -> bool:
        """拖动或程序化改尺寸期间忽略进出，避免假离开打回窄条。"""
        return (
            self._user_dragging
            or self._applying_dock
            or time.monotonic() < self._ignore_hover_until
        )

    def _apply_chrome(self) -> None:
        """悬停时加厚方卡品红外框；不对整卡缩放，避免视觉偏心。"""
        m = self.m
        hover = self._chrome_hover and not self._user_dragging
        docked_strip = bool(self._dock_side and self._reveal != "open")
        base = m.border
        # 折叠窄条用更细边框，避免把内部图标/文字挤没
        if docked_strip:
            pad = max(m.u(0.35), base * 0.45)
        elif hover:
            pad = base * 1.45
        else:
            pad = base
        self._frame_pad = pad
        shell = getattr(self, "face_shell", None)
        if shell is not None:
            shell.padding = pad
            shell.bgcolor = MAGENTA_DEEP if hover else MAGENTA
        self.card.padding = 0
        self.card.bgcolor = MAGENTA_DEEP if hover else MAGENTA
        self.card.border = None
        self.card.border_radius = 0
        if hover and self._phase == "empty":
            self.hint_icon_slot.scale = 1.12
            self.hint_icon.color = MAGENTA_DEEP
            self.hint_text.color = MAGENTA
        else:
            self.hint_icon_slot.scale = 1.0
            self.hint_icon.color = MAGENTA
            self.hint_text.color = MUTED

    def _inner_size(self, fw: float, fh: float) -> tuple[float, float, float]:
        """方卡外壳内的白面尺寸（外壳始终按方卡算，不含下方复制键）。

        :return: (inner_w, inner_h, pad)
        """
        pad = self._frame_pad if self._frame_pad > 0 else self.m.border
        # 半藏窄条：整窗就是壳
        strip = bool(self._dock_side and self._reveal != "open")
        if strip:
            return max(self.m.u(2), fw - pad * 2), max(self.m.u(2), fh - pad * 2), pad
        shell_w = min(fw, self.m.card_w)
        shell_h = min(fh if strip else self.m.card_h, self.m.card_h)
        if self._dock_side and self._reveal == "open":
            shell_w = self.m.card_w
            shell_h = self.m.card_h
        return (
            max(self.m.u(2), shell_w - pad * 2),
            max(self.m.u(2), shell_h - pad * 2),
            pad,
        )

    def _move_window_to_reveal(self) -> None:
        """贴边时把窗贴齐该边，并按档位收成窄条或展开。

        :return: None
        """
        self._sync_visuals()
        left, top = self._window_target_pos()
        fw, fh = self._frame_size()
        self._begin_programmatic_move()
        try:
            self.page.window.left = left
            self.page.window.top = top
            self.page.window.width = fw
            self.page.window.height = fh
            _linux_force_geometry(
                int(round(fw)),
                int(round(fh)),
                int(round(left)),
                int(round(top)),
            )
        finally:
            self._end_programmatic_move()

    def _set_reveal(self, reveal: str, *, move: bool = True) -> None:
        """切换贴边档位；贴边时同步改窗口宽高（窄条 ↔ 方卡）。

        :param reveal: open / hidden
        :param move: 是否贴齐当前边并改尺寸
        :return: None
        """
        if reveal not in {"open", "hidden"}:
            reveal = "open"
        self._reveal = reveal
        if move and self._dock_side:
            self._move_window_to_reveal()
        else:
            self._sync_visuals()

    def _apply_dock_from_pos(
        self, left: float, top: float, *, snap_window: bool, width: float | None = None, height: float | None = None
    ) -> None:
        """按真实窗口矩形决定贴哪条边，以及是否收成窄条。

        未贴边则自由悬浮，不隐藏、不拽回右缘。

        :param left: 窗口 X
        :param top: 窗口 Y
        :param snap_window: 是否立刻按档位移窗
        :param width: 可选真实宽
        :param height: 可选真实高
        :return: None
        """
        # 判边时用「展开态」尺寸，避免半藏窄条误判
        content_w, content_h = self._open_frame_size()
        fw = width if width is not None else content_w
        fh = height if height is not None else content_h
        # 若当前已是窄条，用锚点附近的展开矩形估算
        if self._dock_side and self._reveal != "open" and width is not None:
            if self._dock_side == "right":
                left = max(0.0, self._screen[0] - content_w)
                fw = content_w
            elif self._dock_side == "left":
                left = 0.0
                fw = content_w
            elif self._dock_side == "bottom":
                top = max(0.0, self._screen[1] - content_h)
                fh = content_h
            elif self._dock_side == "top":
                top = 0.0
                fh = content_h
        side = self._pick_dock_side(left, top, fw, fh)
        sw, sh = self._screen

        if side == "left":
            self._dock_side = "left"
            self._anchor_left = 0.0
            self._anchor_top = min(max(top, 0), max(0, sh - content_h))
            self._reveal = "hidden"
        elif side == "right":
            self._dock_side = "right"
            self._anchor_left = max(0.0, sw - content_w)
            self._anchor_top = min(max(top, 0), max(0, sh - content_h))
            self._reveal = "hidden"
        elif side == "top":
            self._dock_side = "top"
            self._anchor_left = min(max(left, 0), max(0, sw - content_w))
            self._anchor_top = 0.0
            self._reveal = "hidden"
        elif side == "bottom":
            self._dock_side = "bottom"
            self._anchor_left = min(max(left, 0), max(0, sw - content_w))
            self._anchor_top = max(0.0, sh - content_h)
            self._reveal = "hidden"
        else:
            self._dock_side = None
            self._reveal = "open"
            self._anchor_left = min(max(left, 0), max(0, sw - content_w))
            self._anchor_top = min(max(top, 0), max(0, sh - content_h))

        if snap_window:
            self._move_window_to_reveal()

    def _persist_pos(self) -> None:
        """把展开态锚点坐标写回设置（不写半隐藏时的屏外坐标）。

        :return: None
        """
        settings = load_settings()
        settings.float_ball_x = float(self._anchor_left)
        settings.float_ball_y = float(self._anchor_top)
        save_settings(settings)

    def _has_file(self) -> bool:
        """卡片内是否正持有文件（含转换中 / 失败）。

        :return: 有文件则为 True
        """
        return self._phase in {"converting", "ready", "error"}

    def _open_frame_size(self) -> tuple[float, float]:
        """窗口宽高：方卡始终正方形；就绪时仅向下长出复制键区域。

        :return: (宽, 高)
        """
        m = self.m
        w, h = m.card_w, m.card_h
        if self._phase in {"ready", "celebrating"}:
            h = m.card_h + m.gap + m.copy_h
        return w, h

    def _decide_internal_copy(self) -> bool:
        """始终下方外置突出，不再用卡内遮盖。

        :return: 恒为 False
        """
        return False

    def _apply_native_frame(self, *, preserve_pos: bool) -> None:
        """按当前 frame 改原生窗口尺寸；preserve_pos 时尽量钉住当前位置。

        :param preserve_pos: True 则不贴边吸附，只夹紧在屏内
        :return: None
        """
        fw, fh = self._frame_size()
        self._ignore_move_until = max(
            self._ignore_move_until, time.monotonic() + 1.0
        )
        self._move_gen += 1
        if not preserve_pos or self._dock_side:
            if self._dock_side:
                self._move_window_to_reveal()
            else:
                self._pin_window_box(move=True)
            return
        sw, sh = self._screen
        left, top = self._anchor_left, self._anchor_top
        geo = _x11_read_own_geometry()
        if geo is not None:
            left, top = float(geo[0]), float(geo[1])
        # 优先向下/右扩展；不够则向上/左退让，始终不改 dock_side
        if left + fw > sw:
            left = max(0.0, sw - fw)
        if top + fh > sh:
            top = max(0.0, sh - fh)
        left = min(max(0.0, left), max(0.0, sw - fw))
        top = min(max(0.0, top), max(0.0, sh - fh))
        self._anchor_left = left
        self._anchor_top = top
        self._begin_programmatic_move()
        try:
            win = self.page.window
            win.width = fw
            win.height = fh
            win.min_width = fw
            win.min_height = fh
            win.max_width = max(fw, self._open_frame_size()[0])
            win.max_height = max(fh, self._open_frame_size()[1])
            win.left = left
            win.top = top
            _linux_force_geometry(
                int(round(fw)),
                int(round(fh)),
                int(round(left)),
                int(round(top)),
            )
        finally:
            self._end_programmatic_move()
        self._sync_visuals()

    def _frame_size(self) -> tuple[float, float]:
        """当前窗口宽高：贴边半藏时收成窄条（仅方卡高/宽），否则完整展开。

        半藏绝不能沿用带复制键的长高，否则会变成一条空白长条。

        :return: (宽, 高)
        """
        m = self.m
        if not self._dock_side or self._reveal == "open":
            return self._open_frame_size()
        strip = self._hide_inset()
        if self._dock_side in {"left", "right"}:
            return strip, m.card_h
        return m.card_w, strip

    def _ball_left(self) -> float:
        """内容区水平位置；窄条不再用负坐标裁切，避免 GTK 布局异常。

        :return: 内容左侧坐标
        """
        return 0.0

    def _ball_top(self) -> float:
        """内容区垂直位置。"""
        return 0.0

    def _copy_pos(self) -> tuple[float, float]:
        """复制键左上角：贴在方卡正下方居中，不遮盖内容。

        :return: (left, top)
        """
        m = self.m
        fw, _fh = self._frame_size()
        copy_w = min(m.copy_w, max(m.u(4), fw - m.u(1.2)))
        return max(0.0, (fw - copy_w) / 2), m.card_h + m.gap

    def _apply_frame_to_controls(self) -> None:
        """同步宿主 / 方卡壳 / 复制层尺寸。

        :return: None
        """
        m = self.m
        fw, fh = self._frame_size()
        strip = bool(self._dock_side and self._reveal != "open")
        pad = self._frame_pad if self._frame_pad > 0 else m.border
        self.card.padding = 0
        self.card.border_radius = 0
        self.card.border = None
        self.card.width = fw
        self.card.height = fh
        self.host.width = fw
        self.host.height = fh
        self.stack.width = fw
        self.stack.height = fh
        if strip:
            shell_w, shell_h = fw, fh
        else:
            shell_w, shell_h = m.card_w, m.card_h
        if getattr(self, "face_shell", None) is not None:
            self.face_shell.width = shell_w
            self.face_shell.height = shell_h
            self.face_shell.left = 0
            self.face_shell.top = 0
            self.face_shell.padding = pad
        if getattr(self, "fx_layer", None) is not None:
            self.fx_layer.width = fw
            self.fx_layer.height = fh
        if self._dropzone is not None:
            self._dropzone.width = fw
            self._dropzone.height = fh

    def _sync_visuals(self) -> None:
        """把状态机映射到控件属性。

        :return: None
        """
        m = self.m
        fw, fh = self._frame_size()
        strip = bool(self._dock_side and self._reveal != "open")
        self._apply_chrome()
        self._apply_frame_to_controls()
        iw, ih, pad = self._inner_size(fw, fh)

        # 方卡白面始终铺满 face_shell 内区，绝不被复制键挤扁
        face_w, face_h = iw, ih

        short = min(face_w, face_h)
        self.face.width = face_w
        self.face.height = face_h
        # face 不是 Stack 子节点，禁止设 left/top（会触发 Error displaying）
        self.face.left = None
        self.face.top = None
        self.face.right = None
        self.face.bottom = None
        self.face.expand = None
        self.face.border_radius = min(m.radius, short * 0.22)
        face_bg = (
            FACE_HOVER
            if self._chrome_hover and self._phase == "empty" and not strip
            else FACE
        )
        self.face.bgcolor = face_bg
        self.face.border = (
            None
            if strip
            else ft.Border.all(
                max(1.0, m.u(0.28 if self._chrome_hover else 0.22)),
                MAGENTA if self._chrome_hover else MAGENTA_SOFT,
            )
        )
        if isinstance(self.face.content, ft.Stack):
            self.face.content.width = face_w
            self.face.content.height = face_h

        self.ball_slot.left = 0
        self.ball_slot.top = 0
        self.ball_slot.width = face_w
        self.ball_slot.height = face_h
        self.core.width = face_w
        self.core.height = face_h
        self.core.bgcolor = face_bg
        if isinstance(self.core.content, ft.Stack):
            self.core.content.width = face_w
            self.core.content.height = face_h
        for layer in (self.hint_box, self.file_box, self.x_box, self.ok_box):
            layer.width = face_w
            layer.height = face_h
        self.hint_text.width = face_w
        self.ok_text.width = face_w

        ring = min(m.ring, short * 0.72)
        self.spin.width = ring
        self.spin.height = ring
        self.spin.border_radius = ring / 2
        hole = max(m.u(2.0), ring * 0.58)
        if isinstance(self.spin.content, ft.Container):
            self.spin.content.width = hole
            self.spin.content.height = hole
            self.spin.content.border_radius = hole / 2
            self.spin.content.bgcolor = face_bg
        self.spin_slot.width = ring
        self.spin_slot.height = ring
        self.spin_slot.left = max(0.0, (face_w - ring) / 2)
        self.spin_slot.top = max(0.0, (face_h - ring) / 2)
        self.spin.opacity = (
            1 if self._phase == "converting" and not strip and short >= ring else 0
        )

        copy_w = min(m.copy_w, max(m.u(4), fw - m.u(1.2)))
        copy_h = m.copy_h
        copy_radius = max(m.u(0.55), copy_h * 0.28)
        cx, cy = self._copy_pos()
        self.copy_box.left = cx
        self.copy_box.top = cy
        self.copy_box.border_radius = copy_radius
        show_copy = self._phase == "ready" and (
            not self._dock_side or self._reveal == "open"
        )
        if self._phase == "celebrating":
            self.copy_box.opacity = 0
            self.copy_box.scale = 0.5
            self.copy_box.width = copy_w
            self.copy_box.height = copy_h
        elif show_copy:
            pulse = 1.04 if self._copy_pulse else 1.0
            self.copy_box.opacity = 1
            self.copy_box.scale = pulse
            self.copy_box.width = copy_w
            self.copy_box.height = copy_h
            self.copy_box.bgcolor = MAGENTA_DEEP if self._copy_pulse else MAGENTA
        else:
            self.copy_box.opacity = 0
            self.copy_box.scale = 0.55
            self.copy_box.width = 0
            self.copy_box.height = 0

        warn = bool(self._warn_until)
        empty = self._phase == "empty"
        celebrating = self._phase == "celebrating"
        # 半藏窄条：只显示紧凑图标（上传 / 文件），不留白
        if strip:
            show_hint = empty and not celebrating
            show_file = self._has_file() and not warn
            show_x = False
        else:
            show_file = self._has_file() and not self._hover_delete and not warn
            show_x = self._has_file() and self._hover_delete
            show_hint = (empty and not celebrating) or warn
        self._set_layer(self.hint_box, show_hint)
        if strip:
            self.hint_text.value = " "
            self.hint_text.visible = False
            self.hint_icon.visible = True
            ico = max(m.u(1.8), min(face_w, face_h) * 0.55)
            self.hint_icon.size = ico
            self.hint_icon_slot.width = ico
            self.hint_icon_slot.height = ico
            # 文件态窄条：图标也缩到可辨认
            self.file_icon.size = ico
            if isinstance(self.file_box.content, ft.Container):
                self.file_box.content.width = ico
                self.file_box.content.height = ico
        elif warn:
            self.hint_text.visible = True
            self.hint_text.value = _tr("float_single_only")
            self.hint_text.color = DANGER
            self.hint_icon.visible = False
            self.hint_icon.size = m.icon
            self.hint_icon_slot.width = m.icon
            self.hint_icon_slot.height = m.icon
            self.file_icon.size = m.icon
        elif empty:
            self.hint_text.visible = True
            self.hint_text.value = _tr("float_drop_hint")
            self.hint_icon.visible = True
            self.hint_icon.size = m.icon
            self.hint_icon_slot.width = m.icon
            self.hint_icon_slot.height = m.icon
            self.file_icon.size = m.icon
        self._set_layer(self.file_box, show_file)
        self._set_layer(self.x_box, show_x)
        self._set_layer(self.ok_box, celebrating and self._reveal == "open")
        if self._phase == "error" and show_file:
            self.file_icon.icon = ft.Icons.ERROR_OUTLINE_ROUNDED
            self.file_icon.color = DANGER
        elif self._phase == "ready" and show_file:
            self.file_icon.icon = ft.Icons.TASK_ALT_ROUNDED
            self.file_icon.color = MAGENTA
        elif self._phase == "converting" and show_file:
            self.file_icon.icon = ft.Icons.HOURGLASS_TOP_ROUNDED
            self.file_icon.color = MAGENTA
        else:
            self.file_icon.icon = ft.Icons.DESCRIPTION_ROUNDED
            self.file_icon.color = MAGENTA
        cursor = ft.MouseCursor.CLICK if show_x or empty else ft.MouseCursor.MOVE
        self.ball_hit.mouse_cursor = cursor

    def _set_layer(self, box: ft.Container, on: bool) -> None:
        """切换圆内一层的显隐缩放。

        :param box: 图层容器
        :param on: 是否显示
        :return: None
        """
        box.opacity = 1 if on else 0
        box.scale = 1 if on else 0.82

    def _on_host_enter(self, _e: ft.ControlEvent) -> None:
        """鼠标进入窗口：悬停反馈；贴边窄条时延迟展成方卡。

        :param _e: 进入事件
        :return: None
        """
        if self._phase == "celebrating" or self._user_dragging:
            return
        self._pointer_over = True
        self._hide_gen += 1
        # 缩放瞬间的假进出：只记账，不改档
        if self._applying_dock or time.monotonic() < self._ignore_hover_until:
            return
        self._chrome_hover = True
        if self._dock_side and self._reveal == "hidden":
            self._expand_gen += 1
            self.page.run_task(self._delayed_expand, self._expand_gen)
        else:
            self._sync_visuals()
            self.page.update()

    def _on_host_exit(self, _e: ft.ControlEvent) -> None:
        """鼠标离开窗口：取消悬停；贴边时延迟收回窄条。

        :param _e: 离开事件
        :return: None
        """
        self._hover_delete = False
        if self._user_dragging:
            return
        # 缩放瞬间假离开：不改 pointer_over，避免随后误收
        if self._applying_dock or time.monotonic() < self._ignore_hover_until:
            return
        self._pointer_over = False
        self._chrome_hover = False
        self._sync_visuals()
        self.page.update()
        if not self._dock_side:
            return
        self._expand_gen += 1
        self._hide_gen += 1
        self.page.run_task(self._delayed_hide, self._hide_gen)

    async def _delayed_expand(self, gen: int) -> None:
        """短暂停留后从窄条展成方卡，若期间已离开则取消。

        :param gen: 展开世代号
        :return: None
        """
        await asyncio.sleep(0.08)
        if gen != self._expand_gen or not self._dock_side or self._user_dragging:
            return
        if not self._pointer_over:
            return
        if self._reveal == "hidden":
            self._set_reveal("open", move=True)
            self._chrome_hover = True
            self._sync_visuals()
            self.page.update()

    async def _delayed_hide(self, gen: int) -> None:
        """短暂停留后收成半藏条，若期间又进入则取消。

        :param gen: 隐藏世代号
        :return: None
        """
        await asyncio.sleep(0.38)
        if gen != self._hide_gen or not self._dock_side or self._user_dragging:
            return
        if self._pointer_over:
            return
        if self._reveal != "hidden":
            self._chrome_hover = False
            self._set_reveal("hidden", move=True)
            self.page.update()

    def _on_ball_enter(self, _e: ft.ControlEvent) -> None:
        """进入卡片内容：只切换红 X，不改窗口尺寸。

        :param _e: 进入事件
        :return: None
        """
        if self._phase == "celebrating" or self._user_dragging:
            return
        if self._applying_dock or time.monotonic() < self._ignore_hover_until:
            return
        if self._has_file() and not self._hover_delete:
            self._hover_delete = True
            self._sync_visuals()
            self.page.update()

    def _on_ball_exit(self, _e: ft.ControlEvent) -> None:
        """离开卡片内容：取消删除态，不改窗口尺寸。

        :param _e: 离开事件
        :return: None
        """
        if self._user_dragging:
            return
        if self._applying_dock or time.monotonic() < self._ignore_hover_until:
            return
        if self._hover_delete:
            self._hover_delete = False
            self._sync_visuals()
            self.page.update()

    def _on_ball_tap(self, _e: ft.ControlEvent) -> None:
        """空闲点击选文件；有文件且悬停时删除。

        :param _e: 点击事件
        :return: None
        """
        if self._phase == "celebrating":
            return
        if self._has_file() and self._hover_delete:
            self._clear(animate_copy=True)
            return
        if self._phase == "empty":
            self.page.run_task(self._pick_one)

    def _on_ball_pan(self, _e: ft.ControlEvent) -> None:
        """在卡片上拖动以移动窗口。

        :param _e: 拖动手势
        :return: None
        """
        # 系统拖入文件时 GestureDetector 也会冒泡 pan，绝不能当成拖窗去贴边
        if self._file_dnd or time.monotonic() < self._ignore_move_until:
            return
        self._user_dragging = True
        self._hide_gen += 1
        self._expand_gen += 1
        # 拖动中先展开方卡，松手后再按真实位置贴边
        if self._dock_side and self._reveal != "open":
            self._set_reveal("open", move=True)
            self.page.update()
        self.page.run_task(self.page.window.start_dragging)

    def _on_window_event(self, e: ft.WindowEvent) -> None:
        """拖动中的 MOVED 防抖：停手后再判断贴边或自由悬浮。

        :param e: 原生窗口事件
        :return: None
        """
        if e.type != ft.WindowEventType.MOVED:
            return
        if self._applying_dock or time.monotonic() < self._ignore_move_until:
            return
        self._move_gen += 1
        self.page.run_task(self._debounced_snap, self._move_gen)

    async def _debounced_snap(self, gen: int) -> None:
        """MOVED 停止约 0.2s 后再吸附，避免拖动途中被拽回右缘。

        仅用户拖完窗口才贴边；拖入文件 / 程序改尺寸引起的 MOVED 一律忽略。

        :param gen: 移动世代号
        :return: None
        """
        await asyncio.sleep(0.2)
        if gen != self._move_gen:
            return
        if self._applying_dock or time.monotonic() < self._ignore_move_until:
            return
        if self._file_dnd or not self._user_dragging:
            return
        self._snap_to_edge()
        self._persist_pos()

    def _snap_to_edge(self) -> None:
        """拖动结束：按真实窗口矩形贴边半隐藏，否则停在当前位置。

        :return: None
        """
        self._user_dragging = False
        real = _x11_read_own_geometry()
        if real is not None:
            left, top, rw, rh = (float(v) for v in real)
            self._apply_dock_from_pos(
                left, top, snap_window=True, width=rw, height=rh
            )
        else:
            left = float(self.page.window.left or 0)
            top = float(self.page.window.top or 0)
            self._apply_dock_from_pos(left, top, snap_window=True)
        self._pin_window_box(move=False)
        self._sync_visuals()
        self.page.update()

    def _on_drag_entered(self, _e: ft.ControlEvent) -> None:
        """系统文件拖入窗口时从窄条展成方卡。

        :param _e: 进入事件
        :return: None
        """
        self._file_dnd = True
        self._user_dragging = False
        self._move_gen += 1
        self._ignore_move_until = time.monotonic() + 2.0
        self._pointer_over = True
        self._hide_gen += 1
        self._expand_gen += 1
        self._chrome_hover = True
        if self._dock_side and self._reveal == "hidden":
            self._set_reveal("open", move=True)
        self._sync_visuals()
        self.page.update()

    def _on_drag_exited(self, _e: ft.ControlEvent) -> None:
        """文件拖出窗口：仅贴边时收回半隐藏。

        :param _e: 离开事件
        :return: None
        """
        self._file_dnd = False
        self._user_dragging = False
        if self._applying_dock or time.monotonic() < self._ignore_hover_until:
            return
        self._pointer_over = False
        self._chrome_hover = False
        self._sync_visuals()
        self.page.update()
        if not self._dock_side:
            return
        if self._phase in {"empty", "ready", "error", "converting"}:
            self._expand_gen += 1
            self._hide_gen += 1
            self.page.run_task(self._delayed_hide, self._hide_gen)

    async def _pick_one(self) -> None:
        """点击空闲圆时弹出单选文件对话框。

        :return: None
        """
        if self._phase != "empty":
            return
        title = _tr("choose_files")
        paths: list[str] = []
        if sys.platform.startswith("linux") and linux_file_dialog.zenity_available():
            picked = await linux_file_dialog.pick_files(
                title=title, allow_multiple=False
            )
            if picked:
                paths = picked
        else:
            files = await self.file_picker.pick_files(allow_multiple=False)
            if files:
                paths = [f.path for f in files if getattr(f, "path", None)]
        self._accept_paths(paths)

    def _accept_paths(self, paths: list[str]) -> None:
        """只收下第一个文件并开始转换。

        :param paths: 拖入或选出的路径
        :return: None
        """
        if self._phase in {"converting", "celebrating"}:
            return
        if not paths:
            return
        extra = len(paths) > 1
        if self._has_file():
            self._clear(animate_copy=True)
        self._path = paths[0]
        self._markdown = None
        self._error = None
        self._phase = "converting"
        self._hover_delete = False
        self._warn_until = 1 if extra else 0
        self._token += 1
        token = self._token
        # 转换过程中忽略假 MOVED，并清掉误触的拖窗标记
        self._user_dragging = False
        self._file_dnd = False
        self._move_gen += 1
        self._ignore_move_until = max(
            self._ignore_move_until, time.monotonic() + 4.0
        )
        # 转换时展开全卡，黄黑旋风完整可见
        if self._dock_side:
            self._reveal = "open"
        self._start_spin()
        self._sync_visuals()
        if self._dock_side:
            self._move_window_to_reveal()
        else:
            # 自由悬浮：钉住当前位置尺寸，绝不贴边
            self._apply_native_frame(preserve_pos=True)
        self.page.update()
        self.page.run_thread(self._convert_worker, self._path, token)
        if extra:
            self.page.run_task(self._flash_single_hint)

    def _convert_worker(self, path: str, token: int) -> None:
        """后台线程调用 MarkItDown。

        :param path: 源文件路径
        :param token: 世代号，用于丢弃过期结果
        :return: None
        """
        outcome = converter.convert_file(path)
        self.page.run_task(self._apply_outcome, outcome, token)

    async def _apply_outcome(self, outcome: converter.ConvertOutcome, token: int) -> None:
        """把转换结果套回界面。

        :param outcome: 转换结果
        :param token: 世代号
        :return: None
        """
        if token != self._token or self._phase != "converting":
            return
        if outcome.ok and outcome.markdown:
            self._markdown = outcome.markdown
            self._error = None
            self._phase = "ready"
            self._internal_copy = self._decide_internal_copy()
            self._start_pulse()
        else:
            self._markdown = None
            self._error = outcome.error or _tr("convert_failed")
            self._phase = "error"
            self._internal_copy = False
        self._user_dragging = False
        self._file_dnd = False
        self._ignore_move_until = max(
            self._ignore_move_until, time.monotonic() + 1.5
        )
        self._sync_visuals()
        # 自由悬浮：就地拉高窗口露出复制键；贴边：贴齐展开
        self._apply_native_frame(preserve_pos=True)
        self.page.update()

    async def _flash_single_hint(self) -> None:
        """多文件时短暂提示只收第一个。

        :return: None
        """
        await asyncio.sleep(1.6)
        self._warn_until = 0
        self._sync_visuals()
        self.page.update()

    def _on_copy(self, _e: ft.ControlEvent) -> None:
        """复制 Markdown，播放礼花，然后清空。

        :param _e: 点击事件
        :return: None
        """
        if self._phase != "ready" or not self._markdown:
            return
        self.page.run_task(self._copy_and_celebrate)

    async def _copy_and_celebrate(self) -> None:
        """写入剪贴板，复制键缩回并播礼花，然后清空。

        :return: None
        """
        text = self._markdown or ""
        try:
            await self.clipboard.set(text)
        except Exception:
            self._phase = "error"
            self._sync_visuals()
            self.page.update()
            return

        # 礼花从当前复制键中心射出（相对 stack / fx_layer）
        cw = float(self.copy_box.width or self.m.copy_w)
        ch = float(self.copy_box.height or self.m.copy_h)
        ox = float(self.copy_box.left or 0) + cw / 2 - self.m.spark_half
        oy = float(self.copy_box.top or 0) + ch / 2 - self.m.spark_half

        docked = bool(self._dock_side)
        self._hide_gen += 1
        self._reveal = "open"
        self._phase = "celebrating"
        self._hover_delete = False
        self._pulse_gen += 1
        self._user_dragging = False
        self._ignore_move_until = time.monotonic() + 2.0
        if docked:
            self._move_window_to_reveal()
        else:
            self._apply_native_frame(preserve_pos=True)
        self._sync_visuals()
        # 庆祝时短暂藏起复制键，露出礼花
        self.copy_box.opacity = 0
        self.copy_box.scale = 0.4
        self.page.update()

        await self._burst_sparks(ox, oy)
        await asyncio.sleep(0.85)
        self._reset_sparks()
        self._clear(animate_copy=False)
        self._internal_copy = False
        if docked:
            self._reveal = "hidden"
            self._move_window_to_reveal()
        else:
            self._apply_native_frame(preserve_pos=True)
        self._sync_visuals()
        self.page.update()

    async def _burst_sparks(self, ox: float, oy: float) -> None:
        """从给定点弹出若干色点（消消乐+礼花）。

        :param ox: 起点 X（点左上）
        :param oy: 起点 Y
        :return: None
        """
        # 确保礼花层盖住复制键区域
        if getattr(self, "fx_layer", None) is not None:
            fw, fh = self._frame_size()
            iw, ih, _ = self._inner_size(fw, fh)
            self.fx_layer.width = iw
            self.fx_layer.height = max(ih, oy + self.m.spark_r + self.m.spark_dot)
        for spark in self.sparks:
            spark.animate_opacity = None
            spark.animate_position = None
            spark.animate_scale = None
            spark.left = ox
            spark.top = oy
            spark.opacity = 1
            spark.scale = 1.35
            spark.visible = True
        self.page.update()
        await asyncio.sleep(0.04)
        fly = ft.Animation(560, ft.AnimationCurve.EASE_OUT_CUBIC)
        fade = ft.Animation(560, ft.AnimationCurve.EASE_OUT)
        pop = ft.Animation(280, ft.AnimationCurve.EASE_OUT_BACK)
        for i, spark in enumerate(self.sparks):
            spark.animate_position = fly
            spark.animate_opacity = fade
            spark.animate_scale = pop
            angle = i * (math.tau / SPARK_N) + 0.18
            radius = self.m.spark_r * (0.85 + 0.35 * ((i % 3) / 2))
            spark.left = ox + radius * math.cos(angle)
            spark.top = oy + radius * math.sin(angle)
            spark.opacity = 0
            spark.scale = 0.2
        self.page.update()
        await asyncio.sleep(0.62)

    def _content_center(self) -> tuple[float, float]:
        """当前白面内容区中心（相对内 stack）。

        :return: (cx, cy)
        """
        fw, fh = self._frame_size()
        iw, ih, pad = self._inner_size(fw, fh)
        strip = bool(self._dock_side and self._reveal != "open")
        if strip or self._phase not in {"ready", "celebrating"}:
            return iw / 2, ih / 2
        face_w = max(self.m.u(2), min(self.m.card_w - pad * 2, iw))
        face_h = max(self.m.u(2), min(self.m.card_h - pad * 2, ih))
        fx = max(0.0, (iw - face_w) / 2)
        return fx + face_w / 2, face_h / 2

    def _reset_sparks(self) -> None:
        """礼花点收回并隐藏。

        :return: None
        """
        cx, cy = self._content_center()
        cx -= self.m.spark_half
        cy -= self.m.spark_half
        for spark in self.sparks:
            spark.animate_opacity = None
            spark.animate_position = None
            spark.animate_scale = None
            spark.opacity = 0
            spark.scale = 0.2
            spark.left = cx
            spark.top = cy
            spark.animate_opacity = ft.Animation(420, ft.AnimationCurve.EASE_OUT)
            spark.animate_position = ft.Animation(
                480, ft.AnimationCurve.EASE_OUT_CUBIC
            )
            spark.animate_scale = ft.Animation(420, ft.AnimationCurve.EASE_OUT)

    def _clear(self, *, animate_copy: bool) -> None:
        """丢掉当前文件，复制键按动画缩回。

        :param animate_copy: 是否走复制键缩回动画（删除时为 True）
        :return: None
        """
        self._token += 1
        self._path = None
        self._markdown = None
        self._error = None
        self._phase = "empty"
        self._hover_delete = False
        self._pulse_gen += 1
        self._copy_pulse = False
        self._warn_until = 0
        self._internal_copy = False
        if not animate_copy:
            self.copy_box.animate_size = None
            self.copy_box.animate_scale = None
            self.copy_box.animate_opacity = None
            self.copy_box.width = 0
            self.copy_box.height = 0
            self.copy_box.opacity = 0
            self.copy_box.scale = 0.2
            self.copy_box.animate_size = ft.Animation(
                260, ft.AnimationCurve.EASE_OUT_CUBIC
            )
            self.copy_box.animate_scale = ft.Animation(
                320, ft.AnimationCurve.EASE_OUT_BACK
            )
            self.copy_box.animate_opacity = ft.Animation(
                200, ft.AnimationCurve.EASE_OUT
            )
        self._sync_visuals()
        self.page.update()

    def _start_spin(self) -> None:
        """开始黄黑旋风旋转。

        :return: None
        """
        self._spinning = True
        self.page.run_task(self._spin_loop, self._token)

    async def _spin_loop(self, token: int) -> None:
        """转换期间持续转圈。

        :param token: 与当前文件世代对齐
        :return: None
        """
        while self._phase == "converting" and token == self._token:
            self.spin.rotate = _rotate_angle(self.spin.rotate) + math.tau
            self.page.update()
            await asyncio.sleep(1.05)
        self._spinning = False

    def _pin_window_box(self, *, move: bool = False) -> None:
        """钉住窗口尺寸；仅 move=True 时才改位置。

        看门狗只改尺寸，绝不拿 Flet 里可能过期的 left/top 去 XMoveResize。

        :param move: 是否强制移到当前 reveal 目标位
        :return: None
        """
        win = self.page.window
        fw, fh = self._frame_size()
        self.page.bgcolor = MAGENTA
        win.bgcolor = MAGENTA
        win.width = fw
        win.height = fh
        win.min_width = fw
        win.min_height = fh
        open_w, open_h = self._open_frame_size()
        win.max_width = max(fw, open_w)
        win.max_height = max(fh, open_h)
        win.maximized = False
        win.full_screen = False
        if move:
            left, top = self._window_target_pos()
            self._begin_programmatic_move()
            try:
                win.left = left
                win.top = top
                _linux_force_geometry(
                    int(round(fw)),
                    int(round(fh)),
                    int(round(left)),
                    int(round(top)),
                )
            finally:
                self._end_programmatic_move()
        else:
            _linux_force_geometry(int(round(fw)), int(round(fh)), None, None)

    async def _boot_spin(self) -> None:
        """等窗口就绪后反复锁定尺寸/透明，再显示窗口。

        :return: None
        """
        try:
            await self.page.window.wait_until_ready_to_show()
        except Exception:
            pass
        win = self.page.window
        for _ in range(6):
            self._pin_window_box(move=True)
            self.page.update()
            await asyncio.sleep(0.08)
            geo = _x11_read_own_geometry()
            if geo is not None:
                _, _, rw, rh = geo
                fw, fh = self._frame_size()
                if abs(rw - fw) <= 8 and abs(rh - fh) <= 8:
                    break
        self._move_window_to_reveal()
        self._sync_visuals()
        win.visible = True
        self.page.update()
        self._pin_window_box(move=True)
        self.page.update()
        self.page.run_task(self._size_watchdog)
        self.page.run_task(self._idle_breath)

    async def _size_watchdog(self) -> None:
        """启动后数秒内：读回尺寸仍偏大时才重试缩放，不改用户位置。

        :return: None
        """
        open_w, open_h = self._open_frame_size()
        for _ in range(30):
            if self._user_dragging:
                await asyncio.sleep(0.2)
                continue
            geo = _x11_read_own_geometry()
            if geo is not None:
                _, _, rw, rh = geo
                if rw > open_w * 1.5 or rh > open_h * 1.5:
                    self._pin_window_box(move=False)
            else:
                self._pin_window_box(move=False)
            await asyncio.sleep(0.2)

    async def _idle_breath(self) -> None:
        """空闲时品红外框厚度轻呼吸，避免整卡缩放导致偏心。

        :return: None
        """
        self._breath_gen += 1
        gen = self._breath_gen
        up = True
        while gen == self._breath_gen:
            can_breathe = (
                self._phase == "empty"
                and self._reveal == "open"
                and not self._dock_side
                and not self._chrome_hover
                and not self._user_dragging
                and not self._pointer_over
            )
            if can_breathe:
                base = self.m.border
                self._frame_pad = base * (1.18 if up else 1.0)
                self.hint_icon_slot.opacity = 1.0 if up else 0.82
                self._apply_frame_to_controls()
                # 同步内白面尺寸
                fw, fh = self._frame_size()
                iw, ih, _ = self._inner_size(fw, fh)
                self.face.width = iw
                self.face.height = ih
                self.ball_slot.width = iw
                self.ball_slot.height = ih
                self.core.width = iw
                self.core.height = ih
                up = not up
                try:
                    self.page.update()
                except Exception:
                    return
                await asyncio.sleep(1.2)
            else:
                up = True
                self.hint_icon_slot.opacity = 1.0
                await asyncio.sleep(0.45)

    def _start_pulse(self) -> None:
        """贴边就绪时让复制键缓慢呼吸。

        :return: None
        """
        self._pulse_gen += 1
        gen = self._pulse_gen
        self.page.run_task(self._pulse_loop, gen)

    async def _pulse_loop(self, gen: int) -> None:
        """复制键 1.0↔1.06 循环，直到状态改变。

        :param gen: 脉冲世代号
        :return: None
        """
        while gen == self._pulse_gen and self._phase == "ready":
            if self._reveal == "open":
                self._copy_pulse = not self._copy_pulse
                self._sync_visuals()
                self.page.update()
            await asyncio.sleep(0.85)
        self._copy_pulse = False


def main(page: ft.Page) -> None:
    """Flet 入口：挂载悬浮窗。

    :param page: Flet 页面
    :return: None
    """
    FloatBallApp(page)
