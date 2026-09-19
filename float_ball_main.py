from __future__ import annotations

import sys
from pathlib import Path

import flet as ft

from app import converter, export_service, linux_file_dialog
from app.i18n import t
from app.settings import load_settings, save_settings, suggested_save_dir
from app.theme import apply_theme


def main(page: ft.Page) -> None:
    settings = load_settings()
    colors = apply_theme(page, settings.color_scheme)
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
    page.services.append(file_picker)

    def remember_dir(directory: str) -> None:
        settings_now = load_settings()
        if settings_now.default_save_dir == directory:
            return
        settings_now.default_save_dir = directory
        save_settings(settings_now)

    async def pick_paths() -> list[str]:
        if sys.platform.startswith("linux") and linux_file_dialog.zenity_available():
            return await linux_file_dialog.pick_files(
                title=t(load_settings().language, "choose_files"),
                allow_multiple=True,
            )
        files = await file_picker.pick_files(allow_multiple=True)
        return [f.path for f in files if getattr(f, "path", None)]

    async def pick_save_path(lang: str, default_name: str, initial: str) -> str | None:
        if sys.platform.startswith("linux") and linux_file_dialog.zenity_available():
            return await linux_file_dialog.save_file(
                title=t(lang, "save_file"),
                default_name=default_name,
                initial_directory=initial,
            )
        return await file_picker.save_file(
            dialog_title=t(lang, "save_file"),
            file_name=default_name,
            initial_directory=initial,
        )

    async def pick_folder(lang: str, initial: str) -> str | None:
        if sys.platform.startswith("linux") and linux_file_dialog.zenity_available():
            return await linux_file_dialog.pick_directory(
                title=t(lang, "choose_export_folder"),
                initial_directory=initial,
            )
        return await file_picker.get_directory_path(
            dialog_title=t(lang, "choose_export_folder"),
            initial_directory=initial,
        )

    async def pick_and_convert(_e: ft.ControlEvent) -> None:
        paths = await pick_paths()
        if not paths:
            return
        settings_now = load_settings()
        lang = settings_now.language
        initial = suggested_save_dir(settings_now)
        status.value = t(lang, "float_working")
        page.update()

        folder: str | None = None
        if len(paths) > 1:
            folder = await pick_folder(lang, initial)
            if not folder:
                status.value = t(lang, "float_ready")
                page.update()
                return
            remember_dir(folder)

        for path in paths:
            outcome = converter.convert_file(path)
            if not outcome.ok or not outcome.markdown:
                status.value = (outcome.error or t(lang, "convert_failed"))[:18]
                page.update()
                continue
            try:
                if folder:
                    result = export_service.export_markdown(
                        settings_now, path, outcome.markdown, save_dir=folder
                    )
                else:
                    suggested = f"{export_service.build_stem(settings_now, path)}.md"
                    dest = await pick_save_path(lang, suggested, initial)
                    if not dest:
                        status.value = t(lang, "float_ready")
                        page.update()
                        return
                    result = export_service.export_to_path(
                        settings_now, path, outcome.markdown, "md", dest
                    )
                    remember_dir(str(Path(dest).expanduser().parent))
                key = "exported_renamed" if result.renamed else "exported"
                status.value = Path(result.path).name[:16]
                page.show_dialog(
                    ft.SnackBar(
                        content=ft.Text(t(lang, key, path=result.path)),
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
