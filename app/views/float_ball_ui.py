"""置顶悬浮球界面：单文件拖入转换，完成后复制 Markdown。

窗口透明无边框；贴边半隐藏用两档展开（感应带微微探出 / 进入圆完全展开）。
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
WHITE = "#FFFFFF"
YELLOW = "#FFD400"
BLACK = "#1A1A1A"
DANGER = "#E11D48"
# 全透明：避免 Linux 上低 alpha 色被合成器画成实心黑底。
HIT_FILL = ft.Colors.TRANSPARENT


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

    官方轻量客户端没有该控件；打包产物、本仓库 ``build/linux`` 客户端或显式环境变量才启用。

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
    # 源码启动时 Flet 常拉起本仓库已编译的 markitdown-gui（含 dropzone）
    built = Path(__file__).resolve().parents[2] / "build" / "linux" / "markitdown-gui"
    if built.is_file():
        return True
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
    """列出本悬浮球相关的顶层 X11 窗口。

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
            # 标题+class 已足够识别悬浮球；外部工具进程没有父子关系时也能改几何
            by_title.append(wid)
    return by_pid + by_title


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
    """读本悬浮球窗口真实几何（取列表中最后一个）。

    :return: (x, y, width, height) 或 None
    """
    ids = _x11_md_window_ids()
    if not ids:
        return None
    return _x11_read_geometry(ids[-1])


def _x11_close_md_windows(*, keep_last: bool = False) -> None:
    """关闭残留的 MD 悬浮球窗口，避免双开叠大黑底。

    :param keep_last: True 时保留列表中最后一个
    :return: None
    """
    if not sys.platform.startswith("linux"):
        return
    try:
        import ctypes
        import ctypes.util
    except ImportError:
        return
    lib_name = ctypes.util.find_library("X11")
    if not lib_name:
        return
    ids = _x11_md_window_ids()
    if keep_last and ids:
        ids = ids[:-1]
    if not ids:
        return
    x11 = ctypes.cdll.LoadLibrary(lib_name)
    x11.XOpenDisplay.restype = ctypes.c_void_p
    display = x11.XOpenDisplay(None)
    if not display:
        return
    try:
        for wid in ids:
            x11.XDestroyWindow(display, ctypes.c_ulong(wid))
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
    try:
        import ctypes
        import ctypes.util
    except ImportError:
        return False
    lib_x11 = ctypes.util.find_library("X11")
    if not lib_x11:
        return False

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

    x11 = ctypes.cdll.LoadLibrary(lib_x11)
    x11.XOpenDisplay.restype = ctypes.c_void_p
    x11.XAllocSizeHints.restype = ctypes.POINTER(XSizeHints)
    x11.XDefaultRootWindow.restype = ctypes.c_ulong
    x11.XInternAtom.restype = ctypes.c_ulong
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
                ctypes.c_ulong(wid),
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
                x11.XSetWMNormalHints(display, ctypes.c_ulong(wid), hints)
                x11.XMoveResizeWindow(
                    display,
                    ctypes.c_ulong(wid),
                    ctypes.c_int(int(left)),
                    ctypes.c_int(int(top)),
                    ctypes.c_uint(width),
                    ctypes.c_uint(height),
                )
            else:
                hints.contents.flags = flags
                x11.XSetWMNormalHints(display, ctypes.c_ulong(wid), hints)
                x11.XResizeWindow(
                    display,
                    ctypes.c_ulong(wid),
                    ctypes.c_uint(width),
                    ctypes.c_uint(height),
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
    lib_x11 = ctypes.util.find_library("X11")
    lib_ext = ctypes.util.find_library("Xext")
    if not lib_x11 or not lib_ext:
        return False

    shape_bounding = 0
    shape_input = 1
    shape_set = 0

    x11 = ctypes.cdll.LoadLibrary(lib_x11)
    xext = ctypes.cdll.LoadLibrary(lib_ext)
    x11.XOpenDisplay.restype = ctypes.c_void_p
    x11.XDefaultRootWindow.restype = ctypes.c_ulong
    x11.XCreatePixmap.restype = ctypes.c_ulong
    x11.XCreateGC.restype = ctypes.c_void_p
    x11.XDefaultScreen.restype = ctypes.c_int
    x11.XRootWindow.restype = ctypes.c_ulong
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
                ctypes.c_ulong(wid),
                shape_bounding,
                0,
                0,
                ctypes.c_ulong(bound),
                shape_set,
            )
            xext.XShapeCombineMask(
                display,
                ctypes.c_ulong(wid),
                shape_input,
                0,
                0,
                ctypes.c_ulong(full),
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
    """悬浮球窗口控制器。"""

    def __init__(self, page: ft.Page) -> None:
        """构建透明置顶小窗并绑定拖放 / 转换 / 复制。

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
        self._move_gen = 0
        self._ignore_move_until = 0.0
        self._user_dragging = False
        self._dropzone: ft.Control | None = None

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
        """设置无边框置顶透明小窗，并尽量锁死客户端尺寸。

        Linux 上 Material Scaffold 默认底色会盖住 ``page.bgcolor``，需一并透明。
        先隐藏再设尺寸，避免首帧出现超大黑底窗。

        :return: None
        """
        page = self.page
        page.title = "MD"
        page.padding = 0
        page.spacing = 0
        page.horizontal_alignment = ft.CrossAxisAlignment.START
        page.vertical_alignment = ft.MainAxisAlignment.START
        page.theme_mode = ft.ThemeMode.LIGHT
        clear = ft.Theme(
            scaffold_bgcolor=ft.Colors.TRANSPARENT,
            canvas_color=ft.Colors.TRANSPARENT,
        )
        page.theme = clear
        page.dark_theme = clear
        page.bgcolor = ft.Colors.TRANSPARENT
        win = page.window
        win.visible = False
        win.width = self.m.win_w
        win.height = self.m.win_h
        win.min_width = self.m.win_w
        win.min_height = self.m.win_h
        win.max_width = self.m.win_w
        win.max_height = self.m.win_h
        win.always_on_top = True
        win.frameless = True
        win.bgcolor = ft.Colors.TRANSPARENT
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
        """组装圆球、旋风、复制键与礼花点。

        :return: None
        """
        ease = ft.Animation(260, ft.AnimationCurve.EASE_OUT_CUBIC)
        pop = ft.Animation(320, ft.AnimationCurve.EASE_OUT_BACK)
        fade = ft.Animation(200, ft.AnimationCurve.EASE_OUT)

        self.hint_text = ft.Text(
            _tr("float_drop_hint"),
            size=self.m.text_sm,
            weight=ft.FontWeight.W_600,
            color=MAGENTA,
            text_align=ft.TextAlign.CENTER,
        )
        self.file_icon = ft.Icon(
            ft.Icons.INSERT_DRIVE_FILE, size=self.m.icon, color=MAGENTA
        )
        self.x_icon = ft.Icon(ft.Icons.CLOSE, size=self.m.x_icon, color=DANGER)
        self.ok_text = ft.Text(
            _tr("float_copy_ok"),
            size=self.m.text_sm,
            weight=ft.FontWeight.W_700,
            color=MAGENTA,
            text_align=ft.TextAlign.CENTER,
        )
        self.hint_box = self._layer(self.hint_text, 1)
        self.file_box = self._layer(self.file_icon, 0)
        self.x_box = self._layer(self.x_icon, 0)
        self.ok_box = self._layer(self.ok_text, 0)

        self.core = ft.Container(
            content=ft.Stack(
                [self.hint_box, self.file_box, self.x_box, self.ok_box],
                width=self.m.ball,
                height=self.m.ball,
            ),
            width=self.m.ball,
            height=self.m.ball,
            bgcolor=WHITE,
            border=ft.Border.all(self.m.border, MAGENTA),
            border_radius=self.m.ball / 2,
            alignment=ft.Alignment.CENTER,
            shadow=ft.BoxShadow(
                blur_radius=self.m.shadow_blur,
                color="#33000000",
                offset=ft.Offset(0, self.m.shadow_y),
            ),
            animate_opacity=fade,
            animate_scale=pop,
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
            width=self.m.ball,
            height=self.m.ball,
            left=0,
            top=self.m.ball_top,
            animate_position=ease,
        )

        self.spin = ft.Container(
            width=self.m.ring,
            height=self.m.ring,
            border_radius=self.m.ring / 2,
            gradient=ft.SweepGradient(
                colors=[YELLOW, BLACK, YELLOW, BLACK, YELLOW],
                stops=[0.0, 0.25, 0.5, 0.75, 1.0],
            ),
            rotate=0,
            opacity=0,
            animate_opacity=fade,
            animate_rotation=ft.Animation(1100, ft.AnimationCurve.LINEAR),
            ignore_interactions=True,
        )
        self.spin_slot = ft.Container(
            content=self.spin,
            width=self.m.ring,
            height=self.m.ring,
            left=0,
            top=self.m.ball_top - (self.m.ring - self.m.ball) / 2,
            animate_position=ease,
            ignore_interactions=True,
        )

        self.copy_label = ft.Text(
            _tr("copy_clipboard"),
            size=self.m.text_md,
            weight=ft.FontWeight.W_700,
            color=WHITE,
        )
        self.copy_box = ft.Container(
            content=self.copy_label,
            alignment=ft.Alignment.CENTER,
            bgcolor=MAGENTA,
            border_radius=self.m.copy_h / 2,
            width=0,
            height=0,
            opacity=0,
            scale=0.2,
            clip_behavior=ft.ClipBehavior.HARD_EDGE,
            animate_opacity=fade,
            animate_scale=pop,
            animate_size=ease,
            animate_position=ease,
            on_click=self._on_copy,
            shadow=ft.BoxShadow(
                blur_radius=self.m.copy_shadow_blur,
                color="#44000000",
                offset=ft.Offset(0, self.m.copy_shadow_y),
            ),
            left=(self.m.win_w - self.m.copy_w) / 2,
            top=self.m.ball_top + self.m.ball + self.m.gap,
        )

        self.sparks: list[ft.Container] = []
        spark_colors = [
            MAGENTA,
            YELLOW,
            WHITE,
            BLACK,
            DANGER,
            MAGENTA,
            YELLOW,
            WHITE,
            YELLOW,
            MAGENTA,
            DANGER,
            BLACK,
        ]
        for i in range(SPARK_N):
            spark = ft.Container(
                width=self.m.spark_dot,
                height=self.m.spark_dot,
                bgcolor=spark_colors[i % len(spark_colors)],
                border_radius=self.m.spark_dot / 2,
                opacity=0,
                scale=0.2,
                left=self.m.win_w / 2,
                top=self.m.ball_top + self.m.ball / 2,
                animate_opacity=ft.Animation(420, ft.AnimationCurve.EASE_OUT),
                animate_position=ft.Animation(480, ft.AnimationCurve.EASE_OUT_CUBIC),
                animate_scale=ft.Animation(420, ft.AnimationCurve.EASE_OUT),
                ignore_interactions=True,
            )
            self.sparks.append(spark)

        self.stack = ft.Stack(
            [
                self.spin_slot,
                self.ball_slot,
                self.copy_box,
                *self.sparks,
            ],
            width=self.m.win_w,
            height=self.m.win_h,
            # 礼花会飞出圆外，不可 HARD_EDGE 裁切
            clip_behavior=ft.ClipBehavior.NONE,
        )
        self.host = ft.GestureDetector(
            content=ft.Container(
                content=self.stack,
                width=self.m.win_w,
                height=self.m.win_h,
                bgcolor=HIT_FILL,
                alignment=ft.Alignment.TOP_LEFT,
            ),
            on_enter=self._on_host_enter,
            on_exit=self._on_host_exit,
            width=self.m.win_w,
            height=self.m.win_h,
        )

    def _layer(self, inner: ft.Control, opacity: float) -> ft.Container:
        """圆内一层可淡入淡出的内容。

        :param inner: 文案或图标
        :param opacity: 初始透明度
        :return: 铺满圆的容器
        """
        return ft.Container(
            content=inner,
            alignment=ft.Alignment.CENTER,
            width=self.m.ball,
            height=self.m.ball,
            padding=ft.Padding.symmetric(horizontal=self.m.pad),
            opacity=opacity,
            scale=1 if opacity else 0.85,
            animate_opacity=180,
            animate_scale=220,
            ignore_interactions=True,
        )

    def _wrap_dropzone(self, content: ft.Control) -> ft.Control:
        """在支持原生拖放的客户端外包一层 Dropzone。

        :param content: 悬浮球根控件
        :return: Dropzone 或原控件
        """
        if not _use_native_dropzone():
            return content
        import flet_dropzone as ftd

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

    def _restore_position(self) -> None:
        """恢复上次坐标；缺省贴在屏幕右侧中部。

        仅贴边时半隐藏（XShape 月牙）；窗口始终留在屏内贴齐该边。

        :return: None
        """
        settings = load_settings()
        sw, sh = self._screen
        top = (sh - self.m.win_h) / 2
        if settings.float_ball_y is not None:
            top = settings.float_ball_y
        top = max(0, min(top, max(0, sh - self.m.win_h)))
        if settings.float_ball_x is not None:
            left = settings.float_ball_x
        else:
            left = sw - self.m.win_w
        left = max(0, min(left, max(0, sw - self.m.win_w)))
        self._anchor_left = left
        self._anchor_top = top
        self._apply_dock_from_pos(left, top, snap_window=True)

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
        """完全隐藏时仍留在屏内的宽度（约半个球）。"""
        return self.m.ball * 0.48

    def _peek_inset(self) -> float:
        """感应探出时多露出一点。"""
        return self._hide_inset() + self.m.peek

    def _window_target_pos(self) -> tuple[float, float]:
        """按贴边方向计算窗口左上角（始终留在屏内贴齐该边）。

        半隐藏靠 XShape 月牙，不再把窗推出屏幕（WM 会夹回来）。
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
        """标记程序化移窗，短暂忽略随后的 MOVED。"""
        self._applying_dock = True
        self._ignore_move_until = time.monotonic() + 0.45

    def _end_programmatic_move(self) -> None:
        """结束程序化移窗标记。"""
        self._applying_dock = False

    def _visible_inset_for_reveal(self) -> float | None:
        """贴边半隐藏/探出时可见宽度；展开或未贴边则为 None（整圆）。"""
        if not self._dock_side or self._reveal == "open":
            return None
        if self._reveal == "peek":
            return self._peek_inset()
        return self._hide_inset()

    def _apply_window_shape(self) -> None:
        """按当前圆（含旋风外接）与贴边档位裁切可见外形。

        :return: None
        """
        fw, fh = self._frame_size()
        # 旋风环略大于球；按环心裁切并略留 2px，避免黄黑环被切边
        pad = 2.0
        ring = self.m.ring + pad * 2
        bx = self._ball_left() + (self.m.ball - ring) / 2
        by = self.m.ball_top + (self.m.ball - ring) / 2
        copy_rect = None
        inset = self._visible_inset_for_reveal()
        # 半隐藏时不画复制键外形；展开且就绪时加上
        if self._phase == "ready" and inset is None:
            cx, cy = self._copy_pos()
            cw = float(self.copy_box.width or 0) or self.m.copy_w
            ch = float(self.copy_box.height or 0) or self.m.copy_h
            if cw > 1 and ch > 1:
                copy_rect = (cx, cy, cw, ch)
        _linux_apply_shape(
            int(round(fw)),
            int(round(fh)),
            bx,
            by,
            ring,
            copy_rect,
            clip_side=self._dock_side if inset is not None else None,
            visible_inset=inset,
        )

    def _move_window_to_reveal(self) -> None:
        """贴边时把窗贴齐该边，并按档位更新月牙形状。

        :return: None
        """
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
            self._apply_window_shape()
        finally:
            self._end_programmatic_move()

    def _set_reveal(self, reveal: str, *, move: bool = False) -> None:
        """切换探出档位；默认只改形状，避免把球拽回旧锚点。

        :param reveal: open / peek / hidden
        :param move: 是否同时贴齐当前边
        :return: None
        """
        self._reveal = reveal
        if move and self._dock_side:
            self._move_window_to_reveal()
        else:
            self._apply_window_shape()

    def _apply_dock_from_pos(
        self, left: float, top: float, *, snap_window: bool, width: float | None = None, height: float | None = None
    ) -> None:
        """按真实窗口矩形决定贴哪条边，以及隐藏方向。

        未贴边则自由悬浮（圆形停在屏幕中间），不隐藏、不拽回右缘。

        :param left: 窗口 X
        :param top: 窗口 Y
        :param snap_window: 是否立刻按档位移窗
        :param width: 可选真实宽
        :param height: 可选真实高
        :return: None
        """
        fw, fh = self._frame_size()
        if width is not None:
            fw = width
        if height is not None:
            fh = height
        side = self._pick_dock_side(left, top, fw, fh)
        sw, sh = self._screen
        content_w, content_h = self._frame_size()

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
        """圆内是否正持有文件（含转换中 / 失败）。

        :return: 有文件则为 True
        """
        return self._phase in {"converting", "ready", "error"}

    def _frame_size(self) -> tuple[float, float]:
        """当前需要的窗口宽高：空闲贴紧环；贴边侧向复制时加宽。

        :return: (宽, 高)
        """
        m = self.m
        w, h = m.win_w, m.win_h
        side_copy = (
            self._phase == "ready"
            and self._dock_side in {"left", "right"}
            and self._reveal != "open"
        )
        if side_copy:
            w = max(w, m.ball + m.side_gap + m.copy_w + m.pad * 2)
        # 无复制键时收短，减少球下方黑区
        if self._phase not in {"ready", "celebrating"}:
            h = m.ball_top + m.ball + m.pad
            w = min(w, m.ring + m.pad * 2)
        return w, h

    def _ball_left(self) -> float:
        """圆的水平位置：常态居中；左右贴边半隐藏时贴外侧，给内侧复制键留空。

        :return: 圆左侧坐标
        """
        fw, _ = self._frame_size()
        side_copy = (
            self._phase == "ready"
            and self._dock_side in {"left", "right"}
            and self._reveal != "open"
        )
        if side_copy and self._dock_side == "left":
            return self.m.pad
        if side_copy and self._dock_side == "right":
            return fw - self.m.ball - self.m.pad
        return (fw - self.m.ball) / 2

    def _copy_pos(self) -> tuple[float, float]:
        """复制键左上角。贴边半隐藏时锚在屏幕内侧。

        :return: (left, top)
        """
        fw, _ = self._frame_size()
        bx = self._ball_left()
        by = self.m.ball_top
        if self._dock_side and self._reveal != "open":
            mid_y = by + (self.m.ball - self.m.copy_h) / 2
            if self._dock_side == "left":
                return bx + self.m.ball + self.m.side_gap, mid_y
            if self._dock_side == "right":
                return bx - self.m.copy_w - self.m.side_gap, mid_y
            if self._dock_side == "top":
                return (fw - self.m.copy_w) / 2, by + self.m.ball + self.m.gap
            if self._dock_side == "bottom":
                return (
                    (fw - self.m.copy_w) / 2,
                    max(0.0, by - self.m.copy_h - self.m.side_gap),
                )
        return (fw - self.m.copy_w) / 2, by + self.m.ball + self.m.gap

    def _apply_frame_to_controls(self) -> None:
        """把 stack/host/dropzone 尺寸同步到当前 frame。

        :return: None
        """
        fw, fh = self._frame_size()
        self.stack.width = fw
        self.stack.height = fh
        inner = self.host.content
        if isinstance(inner, ft.Container):
            inner.width = fw
            inner.height = fh
        self.host.width = fw
        self.host.height = fh
        if self._dropzone is not None:
            self._dropzone.width = fw
            self._dropzone.height = fh

    def _sync_visuals(self) -> None:
        """把状态机映射到控件属性。

        :return: None
        """
        self._apply_frame_to_controls()
        bx = self._ball_left()
        self.ball_slot.left = bx
        self.ball_slot.top = self.m.ball_top
        self.spin_slot.left = bx - (self.m.ring - self.m.ball) / 2
        self.spin_slot.top = self.m.ball_top - (self.m.ring - self.m.ball) / 2
        self.spin.opacity = 1 if self._phase == "converting" else 0

        cx, cy = self._copy_pos()
        self.copy_box.left = cx
        self.copy_box.top = cy
        show_copy = self._phase == "ready"
        if self._phase == "celebrating":
            self.copy_box.opacity = 0
            self.copy_box.scale = 0
            self.copy_box.width = 0
            self.copy_box.height = 0
        elif show_copy:
            pulse = (
                1.06
                if (
                    self._copy_pulse
                    and self._dock_side
                    and self._reveal != "open"
                )
                else 1.0
            )
            self.copy_box.opacity = 1
            self.copy_box.scale = pulse
            self.copy_box.width = self.m.copy_w
            self.copy_box.height = self.m.copy_h
        else:
            self.copy_box.opacity = 0
            self.copy_box.scale = 0.2
            self.copy_box.width = 0
            self.copy_box.height = 0

        warn = bool(self._warn_until)
        empty = self._phase == "empty"
        celebrating = self._phase == "celebrating"
        show_file = self._has_file() and not self._hover_delete and not warn
        show_x = self._has_file() and self._hover_delete
        self._set_layer(self.hint_box, (empty and not celebrating) or warn)
        if warn:
            self.hint_text.value = _tr("float_single_only")
        elif empty:
            self.hint_text.value = _tr("float_drop_hint")
        self._set_layer(self.file_box, show_file)
        self._set_layer(self.x_box, show_x)
        self._set_layer(self.ok_box, celebrating and self._reveal == "open")
        if self._phase == "error" and show_file:
            self.file_icon.color = DANGER
        else:
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
        """鼠标进入窗口（含内侧感应带）时微微探出。

        :param _e: 进入事件
        :return: None
        """
        if self._phase == "celebrating" or self._user_dragging:
            return
        self._hide_gen += 1
        if self._dock_side and self._reveal == "hidden":
            self._set_reveal("peek", move=False)
            self._sync_visuals()
            self.page.update()

    def _on_host_exit(self, _e: ft.ControlEvent) -> None:
        """鼠标离开窗口：仅当前仍贴边时延迟收回半隐藏。

        :param _e: 离开事件
        :return: None
        """
        self._hover_delete = False
        if self._user_dragging or not self._dock_side:
            return
        self._hide_gen += 1
        self.page.run_task(self._delayed_hide, self._hide_gen)

    async def _delayed_hide(self, gen: int) -> None:
        """短暂停留后半隐藏，若期间又进入则取消。

        :param gen: 隐藏世代号
        :return: None
        """
        await asyncio.sleep(0.28)
        if gen != self._hide_gen or not self._dock_side or self._user_dragging:
            return
        if self._reveal != "hidden":
            self._set_reveal("hidden", move=False)
            self._sync_visuals()
            self.page.update()

    def _on_ball_enter(self, _e: ft.ControlEvent) -> None:
        """进入圆：贴边则完全展开；有文件则图标换成红 X。

        :param _e: 进入事件
        :return: None
        """
        if self._phase == "celebrating" or self._user_dragging:
            return
        self._hide_gen += 1
        changed = False
        if self._dock_side and self._reveal != "open":
            self._set_reveal("open", move=False)
            changed = True
        if self._has_file() and not self._hover_delete:
            self._hover_delete = True
            changed = True
        if changed:
            self._sync_visuals()
            self.page.update()

    def _on_ball_exit(self, _e: ft.ControlEvent) -> None:
        """离开圆：取消删除态；仅贴边时退回探出档（不挪窗）。

        :param _e: 离开事件
        :return: None
        """
        if self._user_dragging:
            return
        changed = False
        if self._hover_delete:
            self._hover_delete = False
            changed = True
        if self._dock_side and self._reveal == "open":
            self._set_reveal("peek", move=False)
            changed = True
        if changed:
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
        """在圆上拖动以移动窗口。

        :param _e: 拖动手势
        :return: None
        """
        self._user_dragging = True
        self._hide_gen += 1
        # 拖动中先按整圆显示，松手后再按真实位置贴边
        if self._dock_side and self._reveal != "open":
            self._set_reveal("open", move=False)
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

        :param gen: 移动世代号
        :return: None
        """
        await asyncio.sleep(0.2)
        if gen != self._move_gen:
            return
        if self._applying_dock or time.monotonic() < self._ignore_move_until:
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
        """系统文件拖入窗口（含感应带）时先探出。

        :param _e: 进入事件
        :return: None
        """
        self._hide_gen += 1
        if self._dock_side and self._reveal == "hidden":
            self._set_reveal("peek", move=False)
            self._sync_visuals()
            self.page.update()

    def _on_drag_exited(self, _e: ft.ControlEvent) -> None:
        """文件拖出窗口：仅贴边时收回半隐藏。

        :param _e: 离开事件
        :return: None
        """
        if not self._dock_side or self._user_dragging:
            return
        if self._phase in {"empty", "ready", "error", "converting"}:
            self._hide_gen += 1
            self.page.run_task(self._delayed_hide, self._hide_gen)

    async def _on_dropped(self, e: object) -> None:
        """接收拖放路径。

        :param e: Dropzone 事件
        :return: None
        """
        files = getattr(e, "files", None) or []
        paths: list[str] = []
        for file in files:
            path = getattr(file, "path", None)
            if path and str(path).startswith("/") and not str(path).startswith("blob:"):
                paths.append(str(path))
        self._accept_paths(paths)

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
        # 转换时整圆显示旋风，避免月牙裁切黄黑环
        if self._dock_side:
            self._reveal = "open"
        self._start_spin()
        self._sync_visuals()
        self._apply_window_shape()
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
            self._start_pulse()
        else:
            self._markdown = None
            self._error = outcome.error or _tr("convert_failed")
            self._phase = "error"
        self._sync_visuals()
        self._apply_window_shape()
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

        # 礼花从当前复制键中心射出（贴边时键在球内侧）
        cw = float(self.copy_box.width or self.m.copy_w)
        ch = float(self.copy_box.height or self.m.copy_h)
        ox = float(self.copy_box.left or 0) + cw / 2 - self.m.spark_half
        oy = float(self.copy_box.top or 0) + ch / 2 - self.m.spark_half

        # 庆祝时临时完全展开，避免半隐藏把礼花裁掉
        docked = bool(self._dock_side)
        self._hide_gen += 1
        self._reveal = "open"
        self._phase = "celebrating"
        self._hover_delete = False
        self._pulse_gen += 1
        if docked:
            self._move_window_to_reveal()
        self._sync_visuals()
        self.page.update()

        await self._burst_sparks(ox, oy)
        await asyncio.sleep(0.85)
        self._reset_sparks()
        self._clear(animate_copy=False)
        if docked:
            self._reveal = "hidden"
            self._move_window_to_reveal()
        self._sync_visuals()
        self.page.update()

    async def _burst_sparks(self, ox: float, oy: float) -> None:
        """从给定点弹出若干色点（消消乐+礼花）。

        :param ox: 起点 X（点左上）
        :param oy: 起点 Y
        :return: None
        """
        for spark in self.sparks:
            spark.animate_opacity = None
            spark.animate_position = None
            spark.animate_scale = None
            spark.left = ox
            spark.top = oy
            spark.opacity = 1
            spark.scale = 1.2
        self.page.update()
        await asyncio.sleep(0.03)
        fly = ft.Animation(520, ft.AnimationCurve.EASE_OUT_CUBIC)
        fade = ft.Animation(520, ft.AnimationCurve.EASE_OUT)
        for i, spark in enumerate(self.sparks):
            spark.animate_position = fly
            spark.animate_opacity = fade
            spark.animate_scale = fade
            angle = i * (math.tau / SPARK_N) + 0.2
            spark.left = ox + self.m.spark_r * math.cos(angle)
            spark.top = oy + self.m.spark_r * math.sin(angle)
            spark.opacity = 0
            spark.scale = 0.25
        self.page.update()
        await asyncio.sleep(0.55)

    def _reset_sparks(self) -> None:
        """礼花点收回并隐藏。

        :return: None
        """
        cx = self._ball_left() + self.m.ball / 2 - self.m.spark_half
        cy = self.m.ball_top + self.m.ball / 2 - self.m.spark_half
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
        self.page.bgcolor = ft.Colors.TRANSPARENT
        win.bgcolor = ft.Colors.TRANSPARENT
        win.width = fw
        win.height = fh
        win.min_width = fw
        win.min_height = fh
        win.max_width = max(fw, self.m.win_w)
        win.max_height = max(fh, self.m.win_h)
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
            # 只改尺寸，位置以 X11 真实坐标为准
            _linux_force_geometry(int(round(fw)), int(round(fh)), None, None)
        self._apply_window_shape()

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

    async def _size_watchdog(self) -> None:
        """启动后数秒内：读回尺寸仍偏大时才重试缩放，不改用户位置。

        :return: None
        """
        fw0, fh0 = self._frame_size()
        for _ in range(30):
            if self._user_dragging:
                await asyncio.sleep(0.2)
                continue
            geo = _x11_read_own_geometry()
            if geo is not None:
                _, _, rw, rh = geo
                if rw > fw0 * 1.5 or rh > fh0 * 1.5:
                    self._pin_window_box(move=False)
            else:
                self._pin_window_box(move=False)
            await asyncio.sleep(0.2)

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
            if self._dock_side and self._reveal != "open":
                self._copy_pulse = not self._copy_pulse
                self._sync_visuals()
                self.page.update()
            await asyncio.sleep(0.9)
        self._copy_pulse = False


def main(page: ft.Page) -> None:
    """Flet 入口：挂载悬浮球。

    :param page: Flet 页面
    :return: None
    """
    FloatBallApp(page)
