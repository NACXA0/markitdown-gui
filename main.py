from __future__ import annotations

import flet as ft

from app.settings import load_settings
from app.views.main_view import MainApp


def main(page: ft.Page) -> None:
    page.title = "MarkItDown GUI"
    page.window.width = 1100
    page.window.height = 760
    page.window.min_width = 800
    page.window.min_height = 560
    page.padding = 20

    settings = load_settings()
    app = MainApp(page)
    app.bootstrap(settings)
    page.update()


def run() -> None:
    ft.run(main)


if __name__ == "__main__":
    run()
