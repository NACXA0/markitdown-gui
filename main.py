"""MarkItDown GUI 主窗口入口。

启动 Flet 桌面窗口，加载本地设置并挂载主界面。
"""

import flet as ft

from app.settings import load_settings
from app.views.main_view import MainApp


def main(page: ft.Page) -> None:
    """初始化主窗口尺寸、标题，并引导主应用启动。
    :param page: Flet 提供的应用页面对象
    :return: None
    """
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
    ft.run(main)


if __name__ == "__main__":
    run()
