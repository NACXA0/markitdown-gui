from __future__ import annotations

import sys
from typing import Callable

import flet as ft

from app import linux_file_dialog, mcp_server
from app.i18n import t
from app.settings import AppSettings, default_export_dir, save_settings
from app.theme import apply_theme
from app.views.float_ball import ensure_float_ball


def _btn(control: ft.Control, label: str) -> None:
    control.content = label


class SettingsPage:
    """Full-page settings; every control applies immediately (no Save)."""

    def __init__(
        self,
        page: ft.Page,
        settings: AppSettings,
        on_back: Callable[[], None],
        on_changed: Callable[[AppSettings], None],
        folder_picker: ft.FilePicker,
    ) -> None:
        self.page = page
        self.settings = settings
        self.on_back = on_back
        self.on_changed = on_changed
        self.folder_picker = folder_picker

        self.title = ft.Text("", size=24, weight=ft.FontWeight.BOLD)
        self.btn_back = ft.TextButton("", icon=ft.Icons.ARROW_BACK, on_click=self._back)

        self.lang_dd = ft.Dropdown(
            options=[
                ft.DropdownOption(key="zh", text="中文"),
                ft.DropdownOption(key="en", text="English"),
            ],
            value=settings.language,
            width=420,
            on_select=self._on_language,
        )
        self.save_dir_label = ft.Text("", size=13)
        self.save_dir_text = ft.Text(settings.default_save_dir, size=13, expand=True)
        self.btn_choose_folder = ft.OutlinedButton("", on_click=self._choose_folder)
        self.btn_reset_cache = ft.TextButton("", on_click=self._reset_cache_dir)

        self.mode_label = ft.Text("", size=13)
        self.mode_group = ft.RadioGroup(
            value=settings.convert_mode,
            content=ft.Column([]),
            on_change=self._on_mode,
        )

        self.theme_sw = ft.Switch(
            value=settings.theme == "dark", on_change=self._on_theme
        )
        self.float_sw = ft.Switch(
            value=settings.float_ball, on_change=self._on_float
        )
        self.float_hint = ft.Text("", size=11)
        self.ts_sw = ft.Switch(
            value=settings.timestamp_prefix, on_change=self._on_timestamp
        )
        self.mcp_sw = ft.Switch(
            value=settings.mcp_enabled, on_change=self._on_mcp
        )
        self.mcp_hint = ft.Text("", size=11)
        self.mcp_url = ft.Text("", size=11, visible=settings.mcp_enabled)
        self.mcp_status = ft.Text("", size=11)

        self.root = ft.Container(
            content=ft.Column(
                [
                    ft.Row(
                        [self.btn_back, self.title],
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    ),
                    ft.Divider(),
                    self.lang_dd,
                    self.save_dir_label,
                    ft.Row(
                        [
                            self.save_dir_text,
                            self.btn_choose_folder,
                            self.btn_reset_cache,
                        ],
                        wrap=True,
                    ),
                    self.mode_label,
                    self.mode_group,
                    self.theme_sw,
                    self.float_sw,
                    self.float_hint,
                    self.ts_sw,
                    self.mcp_sw,
                    self.mcp_hint,
                    self.mcp_url,
                    self.mcp_status,
                ],
                spacing=12,
                scroll=ft.ScrollMode.AUTO,
                expand=True,
            ),
            expand=True,
            padding=8,
        )
        self._retranslate()

    def _tr(self, key: str, **kwargs) -> str:
        return t(self.settings.language, key, **kwargs)

    def _persist(self) -> None:
        save_settings(self.settings)
        self.on_changed(self.settings)

    def _retranslate(self) -> None:
        self.title.value = self._tr("settings_title")
        _btn(self.btn_back, self._tr("back"))
        self.lang_dd.label = self._tr("language")
        self.lang_dd.options = [
            ft.DropdownOption(key="zh", text=self._tr("lang_zh")),
            ft.DropdownOption(key="en", text=self._tr("lang_en")),
        ]
        self.save_dir_label.value = self._tr("default_save_dir")
        _btn(self.btn_choose_folder, self._tr("choose_folder"))
        _btn(self.btn_reset_cache, self._tr("use_cache_dir"))
        self.mode_label.value = self._tr("convert_mode")
        current = self.mode_group.value or self.settings.convert_mode
        self.mode_group.content = ft.Column(
            [
                ft.Radio(
                    value="drop_immediate",
                    label=self._tr("mode_drop_immediate"),
                ),
                ft.Radio(
                    value="manual_button",
                    label=self._tr("mode_manual_button"),
                ),
                ft.Radio(
                    value="single_immediate_multi_list",
                    label=self._tr("mode_single_immediate"),
                ),
            ]
        )
        self.mode_group.value = current
        self.theme_sw.label = self._tr("theme")
        self.float_sw.label = self._tr("float_ball")
        self.float_hint.value = self._tr("float_ball_hint")
        self.ts_sw.label = self._tr("timestamp_prefix")
        self.mcp_sw.label = self._tr("mcp_enabled")
        self.mcp_hint.value = self._tr("mcp_hint")
        self._refresh_mcp_texts()

    def _refresh_mcp_texts(self) -> None:
        self.mcp_url.value = (
            f"{self._tr('mcp_url')}: http://127.0.0.1:{self.settings.mcp_port}/mcp\n"
            f"{self._tr('mcp_tools')}"
        )
        self.mcp_url.visible = bool(self.settings.mcp_enabled)
        if self.settings.mcp_enabled and mcp_server.is_running():
            self.mcp_status.value = self._tr("mcp_running")
        elif self.settings.mcp_enabled:
            self.mcp_status.value = self._tr("mcp_starting")
        else:
            self.mcp_status.value = self._tr("mcp_stopped")

    def _back(self, _e: ft.ControlEvent | None = None) -> None:
        self.on_back()

    def _on_language(self, e: ft.ControlEvent) -> None:
        self.settings.language = e.control.value or "zh"
        self._retranslate()
        self._persist()
        self.page.update()

    def _on_mode(self, e: ft.ControlEvent) -> None:
        self.settings.convert_mode = (  # type: ignore[assignment]
            e.control.value or "drop_immediate"
        )
        self._persist()

    def _on_theme(self, e: ft.ControlEvent) -> None:
        self.settings.theme = "dark" if e.control.value else "light"
        apply_theme(self.page, self.settings.theme)
        self._persist()
        self.page.update()

    def _on_float(self, e: ft.ControlEvent) -> None:
        self.settings.float_ball = bool(e.control.value)
        ensure_float_ball(self.settings.float_ball)
        self._persist()

    def _on_timestamp(self, e: ft.ControlEvent) -> None:
        self.settings.timestamp_prefix = bool(e.control.value)
        self._persist()

    def _on_mcp(self, e: ft.ControlEvent) -> None:
        self.settings.mcp_enabled = bool(e.control.value)
        mcp_server.apply_setting(self.settings)
        self._refresh_mcp_texts()
        self._persist()
        self.page.update()

    async def _choose_folder(self, _e: ft.ControlEvent) -> None:
        title = self._tr("default_save_dir")
        path = None
        if sys.platform.startswith("linux") and linux_file_dialog.zenity_available():
            path = await linux_file_dialog.pick_directory(title=title)
        else:
            path = await self.folder_picker.get_directory_path(dialog_title=title)
        if path:
            self.settings.default_save_dir = path
            self.save_dir_text.value = path
            self._persist()
            self.page.update()

    def _reset_cache_dir(self, _e: ft.ControlEvent | None = None) -> None:
        path = str(default_export_dir())
        self.settings.default_save_dir = path
        self.save_dir_text.value = path
        self._persist()
        self.page.update()
