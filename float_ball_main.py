from __future__ import annotations

from pathlib import Path

import flet as ft

from app import converter, export_service
from app.i18n import t
from app.settings import load_settings
from app.theme import apply_theme


def main(page: ft.Page) -> None:
    settings = load_settings()
    colors = apply_theme(page, settings.theme)
    page.title = "MD"
    page.window.width = 88
    page.window.height = 100
    page.window.always_on_top = True
    page.window.frameless = True
    page.window.bgcolor = ft.Colors.TRANSPARENT
    page.bgcolor = ft.Colors.TRANSPARENT
    page.padding = 4

    status = ft.Text(t(settings.language, "float_ready"), size=9, color="white")
    file_picker = ft.FilePicker()

    async def pick_and_convert(_e: ft.ControlEvent) -> None:
        files = await file_picker.pick_files(allow_multiple=True)
        if not files:
            return
        settings_now = load_settings()
        if not settings_now.default_save_dir:
            status.value = t(settings_now.language, "no_folder")
            page.update()
            return
        status.value = t(settings_now.language, "float_working")
        page.update()
        for f in files:
            path = getattr(f, "path", None)
            if not path:
                continue
            outcome = converter.convert_file(path)
            if not outcome.ok or not outcome.markdown:
                status.value = (outcome.error or t(settings_now.language, "convert_failed"))[:18]
                page.update()
                continue
            try:
                result = export_service.export_markdown(
                    settings_now, path, outcome.markdown
                )
                key = "exported_renamed" if result.renamed else "exported"
                status.value = Path(result.path).name[:16]
                page.show_dialog(
                    ft.SnackBar(
                        content=ft.Text(
                            t(settings_now.language, key, path=result.path)
                        ),
                        open=True,
                    )
                )
            except Exception as exc:  # noqa: BLE001
                status.value = str(exc)[:18]
            page.update()
        page.update()

    ball = ft.Container(
        content=ft.Column(
            [
                ft.Text("MD", size=16, weight=ft.FontWeight.BOLD, color="white"),
                status,
            ],
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            spacing=2,
        ),
        width=72,
        height=72,
        alignment=ft.Alignment.CENTER,
        bgcolor=colors["accent"],
        border_radius=36,
        on_click=pick_and_convert,
    )

    page.add(
        ft.WindowDragArea(
            content=ft.Container(content=ball, padding=4),
            maximizable=False,
        )
    )


if __name__ == "__main__":
    ft.run(main)
