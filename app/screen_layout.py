"""屏幕探测与悬浮球响应式布局。

优先相对短边 / 物理毫米；像素仅在窗口几何等不可避免处使用，
并经 ``detect_screen`` 换算以适配不同分辨率与 DPI。
"""

from __future__ import annotations

import os
import re
import subprocess
from dataclasses import dataclass


# —— 相对设计令牌（相对球径）；参考 1080p 上球径约 72px ——
_BALL_MM = 13.0
_BALL_OF_SHORT = 72 / 1080
_BALL_MIN = 48.0
_BALL_MAX = 128.0
_RING_K = 14 / 9
# 窗口尽量贴紧旋风外接方，仅额外留给复制键；缩小 Linux 不透明时的黑边
_WIN_PAD_K = 0.35 / 9
_PEEK_K = 1.25 / 9
_COPY_W_K = 11 / 9
_COPY_H_K = 4.5 / 9
_EDGE_K = 3 / 9
_GAP_K = 1.25 / 9
_SIDE_GAP_K = 0.75 / 9
_BORDER_K = 1 / 9
_ICON_K = 3.75 / 9
_X_ICON_K = 5.75 / 9
_TEXT_SM_K = 1.375 / 9
_TEXT_MD_K = 1.875 / 9
_SPARK_R_K = 5.5 / 9
_SPARK_DOT_K = 1.125 / 9
_SHADOW_BLUR_K = 1.25 / 9
_SHADOW_Y_K = 0.25 / 9
_COPY_SHADOW_BLUR_K = 1 / 9
_COPY_SHADOW_Y_K = 0.125 / 9
_PAD_K = 1 / 9
SPARK_N = 12


def _clamp(value: float, low: float, high: float) -> float:
    """夹到闭区间。

    :param value: 原值
    :param low: 下限
    :param high: 上限
    :return: 夹紧后的值
    """
    return max(low, min(high, value))


@dataclass(frozen=True)
class ScreenInfo:
    """主屏探测结果：逻辑像素、缩放与可选物理尺寸。"""

    width: int
    height: int
    scale: float = 1.0
    width_mm: float | None = None
    height_mm: float | None = None

    @property
    def short(self) -> int:
        """较短边逻辑像素。"""
        return min(self.width, self.height)

    @property
    def px_per_mm(self) -> float | None:
        """水平方向每毫米像素；未知则为 None。"""
        if self.width_mm and self.width_mm > 1:
            return self.width / self.width_mm
        return None

    @property
    def dpi(self) -> float | None:
        """近似 DPI；未知则为 None。"""
        ppm = self.px_per_mm
        return ppm * 25.4 if ppm else None


@dataclass(frozen=True)
class BallLayout:
    """悬浮球一套响应式尺寸（逻辑像素）。"""

    win_w: float
    win_h: float
    ball: float
    ring: float
    peek: float
    copy_w: float
    copy_h: float
    ball_top: float
    edge: float
    gap: float
    side_gap: float
    border: float
    icon: float
    x_icon: float
    text_sm: float
    text_md: float
    spark_r: float
    spark_dot: float
    spark_half: float
    shadow_blur: float
    shadow_y: float
    copy_shadow_blur: float
    copy_shadow_y: float
    pad: float
    unit: float
    screen: ScreenInfo

    def u(self, n: float) -> float:
        """密度倍数 → 逻辑像素（相对本屏算出的 unit）。

        :param n: 设计倍数
        :return: 像素值
        """
        return n * self.unit

    @staticmethod
    def from_screen(screen: ScreenInfo) -> BallLayout:
        """按屏幕短边 / 物理毫米生成布局。

        :param screen: 探测结果
        :return: 布局尺寸
        """
        ppm = screen.px_per_mm
        if ppm:
            ball = _clamp(ppm * _BALL_MM, _BALL_MIN, _BALL_MAX)
        else:
            ball = _clamp(screen.short * _BALL_OF_SHORT, _BALL_MIN, _BALL_MAX)
        # 极高缩放下逻辑坐标已放大时略收敛，避免球过大
        if screen.scale > 1.25:
            ball = _clamp(ball / (0.85 + 0.15 * screen.scale), _BALL_MIN, _BALL_MAX)
        unit = ball / 9.0
        spark_dot = ball * _SPARK_DOT_K
        ring = ball * _RING_K
        pad = ball * _WIN_PAD_K
        copy_w = ball * _COPY_W_K
        copy_h = ball * _COPY_H_K
        gap = ball * _GAP_K
        side_gap = ball * _SIDE_GAP_K
        # 球在窗口上方居中；环略超出球，ball_top 刚好放下环
        ball_top = (ring - ball) / 2 + pad
        # 常态尽量贴紧环/下方复制键；侧向复制时由 UI 动态加宽
        win_w = max(ring + pad * 2, copy_w + pad * 2)
        win_h = ball_top + ball + gap + copy_h + pad
        return BallLayout(
            win_w=win_w,
            win_h=win_h,
            ball=ball,
            ring=ring,
            peek=ball * _PEEK_K,
            copy_w=copy_w,
            copy_h=copy_h,
            ball_top=ball_top,
            edge=ball * _EDGE_K,
            gap=gap,
            side_gap=side_gap,
            border=max(1.0, ball * _BORDER_K),
            icon=ball * _ICON_K,
            x_icon=ball * _X_ICON_K,
            text_sm=ball * _TEXT_SM_K,
            text_md=ball * _TEXT_MD_K,
            spark_r=ball * _SPARK_R_K,
            spark_dot=spark_dot,
            spark_half=spark_dot / 2,
            shadow_blur=ball * _SHADOW_BLUR_K,
            shadow_y=ball * _SHADOW_Y_K,
            copy_shadow_blur=ball * _COPY_SHADOW_BLUR_K,
            copy_shadow_y=ball * _COPY_SHADOW_Y_K,
            pad=ball * _PAD_K,
            unit=unit,
            screen=screen,
        )


def detect_screen() -> ScreenInfo:
    """探测主屏逻辑分辨率、缩放因子与物理毫米（若可得）。

    优先 Gdk；其次 xrandr（含 mm）；再退回 1920×1080。

    :return: ScreenInfo
    """
    env_scale = _env_scale()
    for ver in ("4.0", "3.0"):
        info = _detect_via_gdk(ver, env_scale)
        if info is not None:
            return info
    info = _detect_via_xrandr(env_scale)
    if info is not None:
        return info
    return ScreenInfo(width=1920, height=1080, scale=env_scale or 1.0)


def screen_size() -> tuple[int, int]:
    """兼容旧调用：只返回主屏宽高。

    :return: (宽, 高)
    """
    info = detect_screen()
    return info.width, info.height


def _env_scale() -> float:
    """从环境变量读缩放提示。

    :return: >0 的缩放；没有则 0 表示未知
    """
    for key in ("GDK_SCALE", "QT_SCALE_FACTOR", "GDK_DPI_SCALE"):
        raw = (os.environ.get(key) or "").strip()
        if not raw:
            continue
        try:
            value = float(raw)
        except ValueError:
            continue
        if value > 0:
            return value
    return 0.0


def _detect_via_gdk(ver: str, env_scale: float) -> ScreenInfo | None:
    """经 PyGObject Gdk 读主屏。

    :param ver: Gdk 版本号字符串
    :param env_scale: 环境缩放回退
    :return: ScreenInfo 或 None
    """
    try:
        import gi

        gi.require_version("Gdk", ver)
        from gi.repository import Gdk

        display = Gdk.Display.get_default()
        if display is None:
            return None
        if ver == "4.0":
            monitors = display.get_monitors()
            if not monitors.get_n_items():
                return None
            monitor = monitors.get_item(0)
            geo = monitor.get_geometry()
            scale = float(monitor.get_scale_factor() or 1)
            width_mm = height_mm = None
            try:
                width_mm = float(monitor.get_width_mm() or 0) or None
                height_mm = float(monitor.get_height_mm() or 0) or None
            except Exception:
                pass
            return ScreenInfo(
                width=int(geo.width),
                height=int(geo.height),
                scale=scale or env_scale or 1.0,
                width_mm=width_mm,
                height_mm=height_mm,
            )
        try:
            monitor = display.get_primary_monitor() or display.get_monitor(0)
        except Exception:
            monitor = display.get_monitor(0)
        if monitor is None:
            return None
        geo = monitor.get_geometry()
        scale = 1.0
        try:
            scale = float(monitor.get_scale_factor() or 1)
        except Exception:
            scale = env_scale or 1.0
        width_mm = height_mm = None
        try:
            width_mm = float(monitor.get_width_mm() or 0) or None
            height_mm = float(monitor.get_height_mm() or 0) or None
        except Exception:
            pass
        return ScreenInfo(
            width=int(geo.width),
            height=int(geo.height),
            scale=scale or env_scale or 1.0,
            width_mm=width_mm,
            height_mm=height_mm,
        )
    except Exception:
        return None


def _detect_via_xrandr(env_scale: float) -> ScreenInfo | None:
    """解析 ``xrandr --current`` 的主屏几何与毫米。

    :param env_scale: 环境缩放回退
    :return: ScreenInfo 或 None
    """
    try:
        out = subprocess.check_output(
            ["xrandr", "--current"], text=True, timeout=1.5
        )
    except Exception:
        return None
    primary: ScreenInfo | None = None
    fallback: ScreenInfo | None = None
    line_re = re.compile(
        r"(\d+)x(\d+)\+\d+\+\d+(?:.*?\b(\d+)mm\s*x\s*(\d+)mm)?"
    )
    for line in out.splitlines():
        if " connected" not in line:
            continue
        match = line_re.search(line)
        if not match:
            continue
        info = ScreenInfo(
            width=int(match.group(1)),
            height=int(match.group(2)),
            scale=env_scale or 1.0,
            width_mm=float(match.group(3)) if match.group(3) else None,
            height_mm=float(match.group(4)) if match.group(4) else None,
        )
        if " primary " in line:
            primary = info
            break
        if fallback is None:
            fallback = info
    return primary or fallback
