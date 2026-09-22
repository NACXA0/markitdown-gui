"""悬浮球窗口的模块入口，供 ``python -m app.float_ball_app`` 启动。"""

import os
import sys

# 必须在 import flet / 拉起 Flutter 客户端之前写好，否则 GTK 仍走 Wayland，
# 会出现超大黑底窗且内容挤在左上角。
if sys.platform.startswith("linux") and os.environ.get(
    "MARKITDOWN_FLOAT_BALL_WAYLAND", ""
).strip().lower() not in {"1", "true", "yes", "on"}:
    os.environ["GDK_BACKEND"] = "x11"

import flet as ft

from app.views.float_ball_ui import main as ball_main


def _prefer_x11_backend() -> None:
    """再次确认悬浮球使用 GDK X11 后端。

    :return: None
    """
    if not sys.platform.startswith("linux"):
        return
    if os.environ.get("MARKITDOWN_FLOAT_BALL_WAYLAND", "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }:
        return
    os.environ["GDK_BACKEND"] = "x11"


def main(page: ft.Page) -> None:
    """把页面交给悬浮球界面。

    :param page: Flet 页面
    :return: None
    """
    ball_main(page)


def run() -> None:
    """以桌面小窗方式运行悬浮球。

    :return: None
    """
    _prefer_x11_backend()
    ft.run(main)


if __name__ == "__main__":
    run()
