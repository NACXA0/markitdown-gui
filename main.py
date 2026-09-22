"""MarkItDown GUI 主窗口入口。

启动 Flet 桌面窗口，加载本地设置并挂载主界面。
打包环境下若设置 ``MARKITDOWN_FLOAT_BALL=1``，则改为启动悬浮球窗口。
"""

import os
import sys

_FLOAT_ENV = "MARKITDOWN_FLOAT_BALL"


def _want_float_ball() -> bool:
    """是否应以悬浮球模式启动。

    :return: 环境变量开启则为 True
    """
    return os.environ.get(_FLOAT_ENV, "").strip() in {"1", "true", "yes", "on"}


# 打包二次启动悬浮球时，须在 import flet 前强制 X11。
if _want_float_ball() and sys.platform.startswith("linux"):
    if os.environ.get("MARKITDOWN_FLOAT_BALL_WAYLAND", "").strip().lower() not in {
        "1",
        "true",
        "yes",
        "on",
    }:
        os.environ["GDK_BACKEND"] = "x11"

import flet as ft

from app.settings import load_settings
from app.views.main_view import MainApp


def main(page: ft.Page) -> None:
    """初始化主窗口或悬浮球（打包二次启动时）。

    :param page: Flet 提供的应用页面对象
    :return: None
    """
    if _want_float_ball():
        from app.views.float_ball_ui import main as ball_main

        ball_main(page)
        return

    page.title = "MarkItDown GUI"
    page.window.width = 1100
    page.window.height = 760
    page.window.min_width = 800
    page.window.min_height = 560
    page.padding = 0
    page.spacing = 0

    settings = load_settings()
    app = MainApp(page)
    app.bootstrap(settings)
    page.update()


def run() -> None:
    """以桌面应用方式运行 ``main``。

    :return: None
    """
    if _want_float_ball():
        from app.float_ball_app import run as run_ball

        # 打包二次启动也走同一套 X11/透明窗处理
        run_ball()
        return
    ft.run(main)


if __name__ == "__main__":
    run()
