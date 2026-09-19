from __future__ import annotations

from typing import Callable

import flet as ft

from app import linux_file_dialog, mcp_server
from app.i18n import t
from app.settings import AppSettings, save_settings, suggested_save_dir
from app.theme import SCHEME_IDS, apply_theme, palette, scheme_is_dark, u


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
        self.colors = apply_theme(page, settings.color_scheme)
        page.padding = 0
        page.spacing = 0

        self.title = ft.Text(
            "", theme_style=ft.TextThemeStyle.TITLE_LARGE, weight=ft.FontWeight.W_700
        )
        self.btn_back = ft.TextButton("", icon=ft.Icons.ARROW_BACK, on_click=self._back)
        self.header = ft.Container(
            content=ft.Row(
                [self.btn_back, self.title],
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                spacing=u(0.5),
            ),
            padding=ft.Padding.only(left=u(2), right=u(2), top=0, bottom=u(1)),
        )

        self.general_title = ft.Text("", weight=ft.FontWeight.W_700)
        self.lang_dd = ft.Dropdown(
            options=[
                ft.DropdownOption(key="zh", text="简体中文"),
                ft.DropdownOption(key="en", text="English"),
            ],
            value=settings.language,
            text="简体中文" if settings.language == "zh" else "English",
            enable_search=False,
            editable=False,
            dense=True,
            filled=True,
            on_select=self._on_language,
        )

        self.export_title = ft.Text("", weight=ft.FontWeight.W_700)
        self.save_dir_field = ft.TextField(
            value=settings.default_save_dir,
            dense=True,
            filled=True,
            expand=True,
            on_blur=self._on_save_dir_commit,
            on_submit=self._on_save_dir_commit,
        )
        self.save_dir_hint = ft.Text("", theme_style=ft.TextThemeStyle.BODY_SMALL)
        self.btn_choose_folder = ft.OutlinedButton(
            "", icon=ft.Icons.FOLDER_OPEN, on_click=self._on_choose_folder
        )

        self.convert_title = ft.Text("", weight=ft.FontWeight.W_700)
        self.mode_radios = ft.Column(tight=True, spacing=u(0.25))
        self.mode_group = ft.RadioGroup(
            value=settings.convert_mode,
            content=self.mode_radios,
            on_change=self._on_mode,
        )
        self.ts_sw = ft.Switch(
            value=settings.timestamp_prefix, on_change=self._on_timestamp
        )

        self.appearance_title = ft.Text("", weight=ft.FontWeight.W_700)
        self.scheme_hint = ft.Text("", theme_style=ft.TextThemeStyle.BODY_SMALL)
        self.scheme_grid = ft.ResponsiveRow(
            spacing=u(1),
            run_spacing=u(1),
            columns=12,
        )

        self.mcp_title = ft.Text("", weight=ft.FontWeight.W_700)
        self.mcp_desc = ft.Text("", theme_style=ft.TextThemeStyle.BODY_MEDIUM)
        self.mcp_how = ft.Text("", theme_style=ft.TextThemeStyle.BODY_MEDIUM)
        self.mcp_sw = ft.Switch(
            value=settings.mcp_enabled, on_change=self._on_mcp
        )
        self.mcp_status_label = ft.Text("", theme_style=ft.TextThemeStyle.LABEL_LARGE)
        self.mcp_status = ft.Text("", weight=ft.FontWeight.W_600)
        self.mcp_status_box = ft.Container(padding=u(1.25), border_radius=u(1))
        self.mcp_url_label = ft.Text("", theme_style=ft.TextThemeStyle.LABEL_LARGE)
        self.mcp_url_field = ft.TextField(
            value="",
            read_only=True,
            dense=True,
            filled=True,
            expand=True,
        )
        self.btn_copy_mcp = ft.OutlinedButton("", icon=ft.Icons.CONTENT_COPY)
        self.mcp_tools_heading = ft.Text("", weight=ft.FontWeight.W_600)
        self.mcp_tool_text = ft.Text("", theme_style=ft.TextThemeStyle.BODY_MEDIUM)
        self.mcp_tool_file = ft.Text("", theme_style=ft.TextThemeStyle.BODY_MEDIUM)
        self.mcp_tool_text_box = ft.Container(padding=u(1.25), border_radius=u(1))
        self.mcp_tool_file_box = ft.Container(padding=u(1.25), border_radius=u(1))

        self.general_card = self._card()
        self.export_card = self._card()
        self.convert_card = self._card()
        self.appearance_card = self._card()
        self.mcp_card = self._card()

        self.body = ft.Column(
            [
                self.general_card,
                self.export_card,
                self.convert_card,
                self.appearance_card,
                self.mcp_card,
            ],
            spacing=u(2.5),
            tight=True,
            scroll=ft.ScrollMode.AUTO,
            expand=True,
        )
        self.root = ft.Column(
            [
                self.header,
                ft.Divider(height=1),
                ft.Container(
                    content=self.body,
                    padding=ft.Padding.only(
                        left=u(2), right=u(2), top=u(1.5), bottom=u(2)
                    ),
                    expand=True,
                ),
            ],
            expand=True,
            spacing=0,
            tight=True,
        )
        self._rebuild_cards()
        self._retranslate()
        self._apply_chrome()

    def _card(self) -> ft.Container:
        return ft.Container(
            padding=ft.Padding.symmetric(horizontal=u(2.5), vertical=u(2)),
            border_radius=u(1.5),
        )

    def _rebuild_cards(self) -> None:
        self.general_card.content = ft.Column(
            [self.general_title, ft.Divider(height=1), self.lang_dd],
            spacing=u(1.25),
            tight=True,
        )
        self.export_card.content = ft.Column(
            [
                self.export_title,
                ft.Divider(height=1),
                ft.Row(
                    [self.save_dir_field, self.btn_choose_folder],
                    spacing=u(1),
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                ),
                self.save_dir_hint,
            ],
            spacing=u(1.25),
            tight=True,
        )
        self.convert_card.content = ft.Column(
            [self.convert_title, ft.Divider(height=1), self.mode_group, self.ts_sw],
            spacing=u(1.25),
            tight=True,
        )
        self.appearance_card.content = ft.Column(
            [self.appearance_title, ft.Divider(height=1), self.scheme_grid, self.scheme_hint],
            spacing=u(1.25),
            tight=True,
        )
        self.mcp_status_box.content = ft.Column(
            [self.mcp_status_label, self.mcp_status],
            spacing=u(0.4),
            tight=True,
        )
        self.mcp_tool_text_box.content = self.mcp_tool_text
        self.mcp_tool_file_box.content = self.mcp_tool_file
        self.mcp_card.content = ft.Column(
            [
                self.mcp_title,
                ft.Divider(height=1),
                self.mcp_desc,
                self.mcp_how,
                self.mcp_sw,
                self.mcp_status_box,
                self.mcp_url_label,
                ft.Row(
                    [self.mcp_url_field, self.btn_copy_mcp],
                    spacing=u(1),
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                ),
                self.mcp_tools_heading,
                self.mcp_tool_text_box,
                self.mcp_tool_file_box,
            ],
            spacing=u(1.25),
            tight=True,
        )

    def _tr(self, key: str, **kwargs) -> str:
        return t(self.settings.language, key, **kwargs)

    def _apply_chrome(self) -> None:
        c = self.colors
        self.header.bgcolor = c["surface"]
        self.title.color = c["ink"]
        for heading in (
            self.general_title,
            self.export_title,
            self.convert_title,
            self.appearance_title,
            self.mcp_title,
        ):
            heading.color = c["ink"]
            heading.theme_style = ft.TextThemeStyle.TITLE_LARGE
        self.save_dir_hint.color = c["muted"]
        self.scheme_hint.color = c["muted"]
        self.mcp_desc.color = c["ink"]
        self.mcp_how.color = c["muted"]
        self.mcp_status_label.color = c["muted"]
        self.mcp_status.color = c["ink"]
        self.mcp_url_label.color = c["muted"]
        self.mcp_tools_heading.color = c["ink"]
        self.mcp_tool_text.color = c["ink"]
        self.mcp_tool_file.color = c["ink"]
        self.mcp_status_box.bgcolor = c["paper"]
        self.mcp_status_box.border = ft.Border.all(1, c["line"])
        self.mcp_tool_text_box.bgcolor = c["paper"]
        self.mcp_tool_text_box.border = ft.Border.all(1, c["line"])
        self.mcp_tool_file_box.bgcolor = c["paper"]
        self.mcp_tool_file_box.border = ft.Border.all(1, c["line"])
        self.save_dir_field.bgcolor = c["paper"]
        self.save_dir_field.color = c["ink"]
        self.save_dir_field.border_color = c["line"]
        self.save_dir_field.focused_border_color = c["accent"]
        self.mcp_url_field.bgcolor = c["paper"]
        self.mcp_url_field.color = c["ink"]
        self.mcp_url_field.border_color = c["line"]
        for card in (
            self.general_card,
            self.export_card,
            self.convert_card,
            self.appearance_card,
            self.mcp_card,
        ):
            card.bgcolor = c["surface"]
            card.border = ft.Border.all(1.5, c["line"])
            card.shadow = ft.BoxShadow(
                blur_radius=u(1.5),
                color=c["shadow"],
                offset=ft.Offset(0, 1),
            )

    def _persist(self) -> None:
        save_settings(self.settings)
        self.on_changed(self.settings)

    def _retranslate(self) -> None:
        self.title.value = self._tr("settings_title")
        _btn(self.btn_back, self._tr("back"))
        self.general_title.value = self._tr("section_general")
        self.export_title.value = self._tr("default_save_dir")
        self.convert_title.value = self._tr("section_convert")
        self.appearance_title.value = self._tr("section_appearance")
        self.mcp_title.value = self._tr("section_mcp")
        self.lang_dd.label = self._tr("language")
        self.lang_dd.value = self.settings.language
        self.lang_dd.text = "简体中文" if self.settings.language == "zh" else "English"
        self.save_dir_field.hint_text = self._tr("default_save_dir")
        self.save_dir_hint.value = self._tr("default_save_hint")
        _btn(self.btn_choose_folder, self._tr("choose_folder"))
        current = self.mode_group.value or self.settings.convert_mode
        self.mode_radios.controls = [
            ft.Radio(value="drop_immediate", label=self._tr("mode_drop_immediate")),
            ft.Radio(value="manual_button", label=self._tr("mode_manual_button")),
            ft.Radio(
                value="single_immediate_multi_list",
                label=self._tr("mode_single_immediate"),
            ),
        ]
        self.mode_group.value = current
        self.scheme_hint.value = self._tr("scheme_hint")
        self._refresh_scheme_chips()
        self.ts_sw.label = self._tr("timestamp_prefix")
        self.mcp_desc.value = self._tr("mcp_desc")
        self.mcp_how.value = self._tr("mcp_how")
        self.mcp_sw.label = self._tr("mcp_enabled")
        self.mcp_status_label.value = self._tr("mcp_status_label")
        self.mcp_url_label.value = self._tr("mcp_url")
        self.mcp_tools_heading.value = self._tr("mcp_tools_heading")
        self.mcp_tool_text.value = self._tr("mcp_tool_text")
        self.mcp_tool_file.value = self._tr("mcp_tool_file")
        _btn(self.btn_copy_mcp, self._tr("mcp_copy_url"))
        self._refresh_mcp_texts()

    def _scheme_chip(self, scheme_id: str) -> ft.Control:
        selected = self.settings.color_scheme == scheme_id
        preview = palette(scheme_id)
        return ft.Container(
            content=ft.Column(
                [
                    ft.Container(
                        height=u(2.25),
                        bgcolor=preview["bg"],
                        border_radius=u(0.75),
                        border=ft.Border.all(1, preview["line"]),
                        content=ft.Row(
                            [
                                ft.Container(
                                    width=u(1.5),
                                    height=u(1.5),
                                    bgcolor=preview["accent"],
                                    border_radius=u(0.75),
                                ),
                                ft.Container(
                                    width=u(1.5),
                                    height=u(1.5),
                                    bgcolor=preview["accent_2"],
                                    border_radius=u(0.75),
                                ),
                            ],
                            spacing=u(0.5),
                            alignment=ft.MainAxisAlignment.CENTER,
                        ),
                        alignment=ft.Alignment.CENTER,
                    ),
                    ft.Text(
                        self._tr(f"scheme_{scheme_id}"),
                        theme_style=ft.TextThemeStyle.LABEL_SMALL,
                        color=preview["ink"],
                        text_align=ft.TextAlign.CENTER,
                        no_wrap=True,
                        overflow=ft.TextOverflow.ELLIPSIS,
                    ),
                ],
                spacing=u(0.5),
                tight=True,
                horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
            ),
            padding=u(0.75),
            border_radius=u(1),
            bgcolor=preview["surface"],
            border=ft.Border.all(
                2 if selected else 1,
                preview["accent"] if selected else preview["line"],
            ),
            col={"xs": 6, "sm": 4, "md": 3},
            on_click=lambda _e, sid=scheme_id: self._on_scheme(sid),
        )

    def _refresh_scheme_chips(self) -> None:
        self.scheme_grid.controls = [self._scheme_chip(sid) for sid in SCHEME_IDS]

    def _on_scheme(self, scheme_id: str) -> None:
        self.settings.color_scheme = scheme_id
        self.settings.theme = "dark" if scheme_is_dark(scheme_id) else "light"
        self.colors = apply_theme(self.page, scheme_id)
        self._apply_chrome()
        self._refresh_scheme_chips()
        self._persist()
        self.page.update()

    def _refresh_mcp_texts(self) -> None:
        url = f"http://127.0.0.1:{self.settings.mcp_port}/mcp"
        self.mcp_url_field.value = url
        self.btn_copy_mcp.action = ft.CopyToClipboard(url)
        self.btn_copy_mcp.on_click = self._on_copy_mcp
        if self.settings.mcp_enabled and mcp_server.is_running():
            self.mcp_status.value = self._tr("mcp_running")
        elif self.settings.mcp_enabled:
            self.mcp_status.value = self._tr("mcp_starting")
        else:
            self.mcp_status.value = self._tr("mcp_stopped")

    def _on_copy_mcp(self, _e: ft.ControlEvent | None = None) -> None:
        self.page.show_dialog(
            ft.SnackBar(content=ft.Text(self._tr("copy_ok")), open=True)
        )

    def _back(self, _e: ft.ControlEvent | None = None) -> None:
        self.on_back()

    def _on_language(self, e: ft.ControlEvent) -> None:
        self.settings.language = e.control.value or "zh"
        self.lang_dd.text = "简体中文" if self.settings.language == "zh" else "English"
        self._retranslate()
        self._persist()
        self.page.update()

    def _on_mode(self, e: ft.ControlEvent) -> None:
        self.settings.convert_mode = (  # type: ignore[assignment]
            e.control.value or "drop_immediate"
        )
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

    def _on_save_dir_commit(self, _e: ft.ControlEvent | None = None) -> None:
        path = (self.save_dir_field.value or "").strip()
        if self.settings.default_save_dir == path:
            return
        self.settings.default_save_dir = path
        self._persist()

    def _on_choose_folder(self, _e: ft.ControlEvent | None = None) -> None:
        self.page.run_task(self._choose_folder)

    async def _choose_folder(self) -> None:
        title = self._tr("default_save_dir")
        initial = suggested_save_dir(self.settings)
        path = None
        try:
            path = await linux_file_dialog.pick_directory(
                title=title, initial_directory=initial
            )
        except linux_file_dialog.DialogUnavailable:
            try:
                path = await self.folder_picker.get_directory_path(
                    dialog_title=title, initial_directory=initial
                )
            except Exception:
                path = None
        if path:
            self.settings.default_save_dir = path
            self.save_dir_field.value = path
            self._persist()
            self.page.update()
