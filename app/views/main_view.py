from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable
import sys

import flet as ft
import flet_dropzone as ftd

from app import converter, export_service, linux_file_dialog, mcp_server
from app.i18n import t
from app.settings import AppSettings
from app.theme import apply_theme
from app.views.float_ball import ensure_float_ball
from app.views.settings_view import SettingsPage


def _btn_label(control: ft.Control, label: str) -> None:
    """Flet 0.86+ buttons use `content`, not `text`."""
    control.content = label


@dataclass
class QueueItem:
    path: str
    name: str
    selected: bool = True
    status: str = "pending"
    markdown: str | None = None
    error: str | None = None
    id: str = field(default_factory=lambda: "")

    def __post_init__(self) -> None:
        if not self.id:
            self.id = f"{self.path}-{id(self)}"


class MainApp:
    def __init__(self, page: ft.Page) -> None:
        self.page = page
        self.settings = AppSettings()
        self.items: list[QueueItem] = []
        self.active_id: str | None = None
        self.busy = False
        self.preview_mode = "source"
        self.export_format = "md"
        self.file_view_mode = "list"  # list | cards
        self.dragging = False
        self.colors = apply_theme(page, "light")
        self._left_panel_width = 420

        self.file_picker = ft.FilePicker()
        self.folder_picker = ft.FilePicker()
        self.clipboard = ft.Clipboard()
        page.services.extend(
            [self.file_picker, self.folder_picker, self.clipboard]
        )
        page.on_keyboard_event = self._on_keyboard

        self.title_text = ft.Text("", size=28, weight=ft.FontWeight.BOLD)
        self.tagline_text = ft.Text("", size=13)
        self.preview_title = ft.Text("", size=12, weight=ft.FontWeight.W_600)
        self.status_bar = ft.Text("", size=12)

        self.preview_body = ft.TextField(
            multiline=True,
            min_lines=18,
            max_lines=36,
            read_only=True,
            expand=True,
            text_size=13,
        )
        self.preview_md = ft.Markdown(
            "",
            selectable=True,
            extension_set=ft.MarkdownExtensionSet.GITHUB_WEB,
            expand=True,
        )
        self.preview_stack = ft.Column(
            [self.preview_body], expand=True, scroll=ft.ScrollMode.AUTO
        )

        self.btn_convert_all = ft.Button(
            "", on_click=lambda e: self._convert_targets(False)
        )
        self.btn_convert_sel = ft.OutlinedButton(
            "", on_click=lambda e: self._convert_targets(True)
        )
        self.btn_export_all = ft.OutlinedButton(
            "", on_click=lambda e: self._export_all()
        )
        self.btn_clear = ft.TextButton("", on_click=lambda e: self._clear())
        self.btn_settings = ft.IconButton(
            ft.Icons.SETTINGS, on_click=self._open_settings
        )
        self.btn_export_one = ft.Button("", on_click=lambda e: self._export_one())
        self.btn_copy = ft.OutlinedButton("", on_click=self._copy_preview)
        self.btn_add_more = ft.TextButton("", on_click=self._browse)
        self.format_dd = ft.Dropdown(
            options=[
                ft.DropdownOption(key="md", text="Markdown"),
                ft.DropdownOption(key="docx", text="DOCX"),
                ft.DropdownOption(key="pdf", text="PDF"),
                ft.DropdownOption(key="html", text="HTML"),
            ],
            value="md",
            width=160,
            on_select=self._on_format_change,
        )
        self.mode_source = ft.Button(
            "", on_click=lambda e: self._set_preview_mode("source")
        )
        self.mode_render = ft.OutlinedButton(
            "", on_click=lambda e: self._set_preview_mode("rendered")
        )
        self.view_cards_btn = ft.Button(
            "", on_click=lambda e: self._set_file_view("cards")
        )
        self.view_list_btn = ft.OutlinedButton(
            "", on_click=lambda e: self._set_file_view("list")
        )

        self.btn_choose = ft.OutlinedButton(
            "", icon=ft.Icons.FOLDER_OPEN, on_click=self._browse
        )
        self.empty_drop_icon = ft.Icon(ft.Icons.UPLOAD_FILE, size=56)
        self.empty_drop_title = ft.Text(
            "", size=22, weight=ft.FontWeight.W_600, text_align=ft.TextAlign.CENTER
        )
        self.empty_drop_hint = ft.Text("", size=13, text_align=ft.TextAlign.CENTER)
        self.empty_drop_col = ft.Column(
            [
                self.empty_drop_icon,
                self.empty_drop_title,
                self.empty_drop_hint,
                self.btn_choose,
            ],
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            spacing=10,
        )
        self.file_list = ft.Column(spacing=6, expand=True, scroll=ft.ScrollMode.AUTO)
        self.file_stage = ft.Container(
            content=self.file_list,
            expand=True,
            padding=16,
            border_radius=16,
            alignment=ft.Alignment.CENTER,
            on_click=self._browse,
            ink=True,
        )
        self.dropzone = ftd.Dropzone(
            content=self.file_stage,
            width=self._left_panel_width,
            expand=False,
            on_dropped=self._on_dropped,
            on_entered=self._on_drag_entered,
            on_exited=self._on_drag_exited,
        )

        self.toolbar = ft.Row(
            [
                ft.Row(
                    [
                        self.btn_convert_all,
                        self.btn_convert_sel,
                        self.btn_export_all,
                        self.btn_clear,
                    ],
                    spacing=8,
                ),
                ft.Row(
                    [
                        self.view_cards_btn,
                        self.view_list_btn,
                        self.btn_add_more,
                    ],
                    spacing=8,
                ),
            ],
            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
        )

        self.preview_panel = ft.Container(
            content=ft.Column(
                [
                    ft.Row(
                        [
                            self.preview_title,
                            ft.Row(
                                [
                                    self.mode_source,
                                    self.mode_render,
                                    self.format_dd,
                                    self.btn_copy,
                                    self.btn_export_one,
                                ],
                                spacing=6,
                                wrap=True,
                            ),
                        ],
                        alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                    ),
                    self.preview_stack,
                ],
                expand=True,
            ),
            padding=12,
            border_radius=16,
            expand=True,
        )

        self.body_row = ft.Row(
            [self.dropzone, self.preview_panel],
            expand=True,
            spacing=12,
            vertical_alignment=ft.CrossAxisAlignment.STRETCH,
        )

        self.root = ft.Container(
            content=ft.Column(
                [
                    ft.Row(
                        [
                            ft.Column(
                                [self.title_text, self.tagline_text],
                                spacing=2,
                                expand=True,
                            ),
                            self.btn_settings,
                        ],
                        alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                    ),
                    self.toolbar,
                    self.body_row,
                    self.status_bar,
                ],
                expand=True,
                spacing=12,
            ),
            expand=True,
            border_radius=12,
            padding=0,
        )
        # Shell swaps between main UI and full-page settings.
        self.shell = ft.Container(content=self.root, expand=True)
        page.add(self.shell)

    def bootstrap(self, settings: AppSettings) -> None:
        self.settings = settings
        self.colors = apply_theme(self.page, settings.theme)
        self._apply_chrome()
        self._retranslate()
        self._refresh_input_zone()
        self._refresh_preview()
        if settings.mcp_enabled:
            mcp_server.apply_setting(settings)
        ensure_float_ball(settings.float_ball)
        self.status_bar.value = self._tr("drop_panel_ready")

    def _on_drag_entered(self, _e: ft.ControlEvent | None = None) -> None:
        self.dragging = True
        self._style_drag_chrome()
        self._sync_drop_copy()
        self.page.update()

    def _on_drag_exited(self, _e: ft.ControlEvent | None = None) -> None:
        self.dragging = False
        self._style_drag_chrome()
        self._sync_drop_copy()
        self.page.update()

    async def _on_dropped(self, e: ftd.DropzoneEvent) -> None:
        paths: list[str] = []
        for file in e.files or []:
            path = getattr(file, "path", None)
            if path and str(path).startswith("/") and not str(path).startswith("blob:"):
                paths.append(str(path))
        self.dragging = False
        self._style_drag_chrome()
        if paths:
            self.add_paths(paths)
            self.snack(self._tr("drop_received", count=len(paths)))
        else:
            self._refresh_input_zone()
            self.page.update()

    def _style_drag_chrome(self) -> None:
        c = self.colors
        if self.dragging:
            self.root.border = ft.Border.all(3, c["accent"])
            self.root.bgcolor = c["accent_soft"]
        else:
            self.root.border = None
            self.root.bgcolor = None
        self._style_input_shell()

    def _tr(self, key: str, **kwargs) -> str:
        return t(self.settings.language, key, **kwargs)

    def _apply_chrome(self) -> None:
        c = self.colors
        self.page.bgcolor = c["bg"]
        self.title_text.color = c["ink"]
        self.tagline_text.color = c["muted"]
        self.preview_title.color = c["muted"]
        self.status_bar.color = c["muted"]
        self.preview_panel.bgcolor = c["surface"]
        self.preview_panel.border = ft.Border.all(1, c["line"])
        self.empty_drop_icon.color = c["accent"]
        self.empty_drop_title.color = c["ink"]
        self.empty_drop_hint.color = c["muted"]
        self._style_input_shell()

    def _style_input_shell(self) -> None:
        c = self.colors
        border_color = c["accent"] if self.dragging else c["line"]
        self.file_stage.bgcolor = c["accent_soft"] if self.dragging else c["surface"]
        self.file_stage.border = ft.Border.all(2, border_color)

    def _sync_drop_copy(self) -> None:
        self.empty_drop_title.value = (
            self._tr("drop_active") if self.dragging else self._tr("drop_title")
        )
        self.empty_drop_hint.value = self._tr("drop_hint")

    def _retranslate(self) -> None:
        self.page.title = self._tr("app_name")
        self.title_text.value = self._tr("app_name")
        self.tagline_text.value = self._tr("tagline")
        self.preview_title.value = self._tr("preview").upper()
        _btn_label(self.btn_convert_all, self._tr("convert_all"))
        _btn_label(self.btn_convert_sel, self._tr("convert_selected"))
        _btn_label(self.btn_export_all, self._tr("export_all"))
        _btn_label(self.btn_clear, self._tr("clear_queue"))
        _btn_label(self.btn_export_one, self._tr("export_one"))
        _btn_label(self.btn_copy, self._tr("copy_clipboard"))
        _btn_label(self.btn_add_more, self._tr("add_more"))
        _btn_label(self.mode_source, self._tr("source"))
        _btn_label(self.mode_render, self._tr("rendered"))
        _btn_label(self.view_cards_btn, self._tr("view_cards"))
        _btn_label(self.view_list_btn, self._tr("view_list"))
        _btn_label(self.btn_choose, self._tr("choose_files"))
        self._sync_drop_copy()
        self.format_dd.options = [
            ft.DropdownOption(key="md", text=self._tr("format_md")),
            ft.DropdownOption(key="docx", text=self._tr("format_docx")),
            ft.DropdownOption(key="pdf", text=self._tr("format_pdf")),
            ft.DropdownOption(key="html", text=self._tr("format_html")),
        ]

    def snack(self, message: str) -> None:
        self.status_bar.value = message
        self.page.update()

    async def _browse(self, _e: ft.ControlEvent | None = None) -> None:
        title = self._tr("choose_files")
        paths: list[str] = []
        # Linux: Zenity is reliable under Wayland; Flet FilePicker often times out.
        if sys.platform.startswith("linux") and linux_file_dialog.zenity_available():
            paths = await linux_file_dialog.pick_files(
                title=title, allow_multiple=True
            )
        else:
            try:
                files = await self.file_picker.pick_files(allow_multiple=True)
                paths = [f.path for f in files if getattr(f, "path", None)]
            except Exception as exc:  # noqa: BLE001
                self.snack(self._tr("picker_failed", error=str(exc)))
                return
        self.add_paths(paths)

    async def _copy_preview(self, _e: ft.ControlEvent | None = None) -> None:
        item = self._active()
        text = ""
        if item and item.markdown:
            text = item.markdown
        elif self.preview_body.value:
            text = self.preview_body.value
        if not text or text in {
            self._tr("no_preview"),
            self._tr("converting"),
        }:
            self.snack(self._tr("copy_empty"))
            return
        try:
            await self.clipboard.set(text)
            self.snack(self._tr("copy_ok"))
        except Exception as exc:  # noqa: BLE001
            self.snack(self._tr("copy_failed", error=str(exc)))

    def add_paths(self, paths: list[str]) -> None:
        existing = {i.path for i in self.items}
        added: list[QueueItem] = []
        for path in paths:
            if not path or path in existing:
                continue
            item = QueueItem(path=path, name=Path(path).name)
            self.items.append(item)
            added.append(item)
            existing.add(path)
        if not added:
            self._style_input_shell()
            self._refresh_input_zone()
            self.page.update()
            return

        # Prefer newly added file as active
        self.active_id = added[0].id
        self._refresh_input_zone()
        self._refresh_preview()

        # Single file: always convert immediately. Multi: follow convert_mode.
        should_convert = len(self.items) == 1 or self.settings.convert_mode in {
            "drop_immediate",
            "single_immediate_multi_list",
        }
        if should_convert:
            self.page.run_thread(self._convert_items, added)
        self.page.update()

    def _set_file_view(self, mode: str) -> None:
        self.file_view_mode = mode
        self._refresh_input_zone()
        self.page.update()

    def _status_label(self, item: QueueItem) -> tuple[str, str]:
        status_key = {
            "pending": "status_pending",
            "converting": "status_converting",
            "done": "status_done",
            "error": "status_error",
        }.get(item.status, "status_pending")
        color = {
            "pending": self.colors["muted"],
            "converting": "#9A6B16",
            "done": self.colors["accent"],
            "error": self.colors["danger"],
        }.get(item.status, self.colors["muted"])
        text = self._tr(status_key)
        if item.error:
            text = f"{text} — {item.error}"
        return text, color

    def _make_remove(self, item_id: str) -> Callable:
        def _remove(_e: ft.ControlEvent) -> None:
            self.items = [i for i in self.items if i.id != item_id]
            if self.active_id == item_id:
                self.active_id = self.items[0].id if self.items else None
            self._refresh_input_zone()
            self._refresh_preview()
            self.page.update()

        return _remove

    def _make_select(self, item_id: str) -> Callable:
        def _select(_e: ft.ControlEvent) -> None:
            self.active_id = item_id
            self._refresh_input_zone()
            self._refresh_preview()
            self.page.update()

        return _select

    def _make_toggle(self, item_id: str) -> Callable:
        def _toggle(e: ft.ControlEvent) -> None:
            for it in self.items:
                if it.id == item_id:
                    it.selected = bool(e.control.value)
                    break

        return _toggle

    def _file_icon(self, name: str) -> str:
        ext = Path(name).suffix.lower()
        mapping = {
            ".pdf": ft.Icons.PICTURE_AS_PDF,
            ".doc": ft.Icons.DESCRIPTION,
            ".docx": ft.Icons.DESCRIPTION,
            ".ppt": ft.Icons.SLIDESHOW,
            ".pptx": ft.Icons.SLIDESHOW,
            ".xls": ft.Icons.TABLE_CHART,
            ".xlsx": ft.Icons.TABLE_CHART,
            ".html": ft.Icons.LANGUAGE,
            ".htm": ft.Icons.LANGUAGE,
            ".png": ft.Icons.IMAGE,
            ".jpg": ft.Icons.IMAGE,
            ".jpeg": ft.Icons.IMAGE,
            ".webp": ft.Icons.IMAGE,
            ".zip": ft.Icons.FOLDER_ZIP,
        }
        return mapping.get(ext, ft.Icons.INSERT_DRIVE_FILE)

    def _file_rows(self) -> list[ft.Control]:
        header = ft.Text(
            self._tr("files_count", count=len(self.items)),
            size=13,
            weight=ft.FontWeight.W_600,
            color=self.colors["muted"],
        )
        if self.file_view_mode == "list":
            return [header, *[self._list_row_for(i) for i in self.items]]
        return [
            header,
            ft.Row(
                [self._card_for(i) for i in self.items],
                wrap=True,
                spacing=10,
                run_spacing=10,
            ),
        ]

    def _card_for(self, item: QueueItem) -> ft.Control:
        status, color = self._status_label(item)
        active = item.id == self.active_id
        return ft.Container(
            content=ft.Column(
                [
                    ft.Row(
                        [
                            ft.Checkbox(
                                value=item.selected,
                                on_change=self._make_toggle(item.id),
                            ),
                            ft.Icon(
                                self._file_icon(item.name),
                                color=self.colors["accent"],
                            ),
                            ft.Container(expand=True),
                            ft.IconButton(
                                ft.Icons.CLOSE,
                                icon_size=16,
                                tooltip=self._tr("remove_file"),
                                on_click=self._make_remove(item.id),
                            ),
                        ]
                    ),
                    ft.Text(
                        item.name,
                        size=14,
                        weight=ft.FontWeight.W_600,
                        max_lines=2,
                        overflow=ft.TextOverflow.ELLIPSIS,
                    ),
                    ft.Text(status, size=11, color=color),
                ],
                spacing=6,
            ),
            padding=12,
            border_radius=14,
            bgcolor=self.colors["accent_soft"] if active else self.colors["bg"],
            border=ft.Border.all(
                1, self.colors["accent"] if active else self.colors["line"]
            ),
            width=170,
            on_click=self._make_select(item.id),
            ink=True,
        )

    def _list_row_for(self, item: QueueItem) -> ft.Control:
        status, color = self._status_label(item)
        active = item.id == self.active_id
        return ft.Container(
            content=ft.Row(
                [
                    ft.Checkbox(
                        value=item.selected,
                        on_change=self._make_toggle(item.id),
                    ),
                    ft.Icon(self._file_icon(item.name), color=self.colors["accent"]),
                    ft.Column(
                        [
                            ft.Text(
                                item.name,
                                size=13,
                                weight=ft.FontWeight.W_600,
                                color=self.colors["ink"],
                                max_lines=1,
                                overflow=ft.TextOverflow.ELLIPSIS,
                            ),
                            ft.Text(
                                item.path,
                                size=11,
                                color=self.colors["muted"],
                                max_lines=1,
                                overflow=ft.TextOverflow.ELLIPSIS,
                            ),
                            ft.Text(status, size=11, color=color),
                        ],
                        spacing=2,
                        expand=True,
                    ),
                    ft.IconButton(
                        ft.Icons.CLOSE,
                        icon_size=16,
                        tooltip=self._tr("remove_file"),
                        on_click=self._make_remove(item.id),
                    ),
                ],
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            padding=10,
            border_radius=12,
            bgcolor=self.colors["accent_soft"] if active else self.colors["bg"],
            border=ft.Border.all(
                1.5 if active else 1,
                self.colors["accent"] if active else self.colors["line"],
            ),
            on_click=self._make_select(item.id),
            ink=True,
        )

    def _refresh_input_zone(self) -> None:
        n = len(self.items)
        has_files = n > 0
        self.dropzone.width = self._left_panel_width
        self.btn_convert_all.disabled = not has_files
        self.btn_convert_sel.disabled = not has_files
        self.btn_export_all.disabled = not has_files
        self.btn_clear.disabled = not has_files
        self.view_cards_btn.disabled = not has_files or self.file_view_mode == "cards"
        self.view_list_btn.disabled = not has_files or self.file_view_mode == "list"

        if has_files:
            self.file_stage.alignment = ft.Alignment.TOP_LEFT
            self.file_stage.on_click = None
            self.file_list.controls = self._file_rows()
        else:
            self.file_stage.alignment = ft.Alignment.CENTER
            self.file_stage.on_click = self._browse
            self.file_list.controls = [self.empty_drop_col]

        self._style_input_shell()
        self._sync_drop_copy()

    def _active_index(self) -> int:
        if not self.items:
            return -1
        for i, item in enumerate(self.items):
            if item.id == self.active_id:
                return i
        return 0

    def _select_index(self, index: int) -> None:
        if not self.items:
            return
        index = max(0, min(index, len(self.items) - 1))
        self.active_id = self.items[index].id
        self._refresh_input_zone()
        self._refresh_preview()
        self.page.update()

    def _on_keyboard(self, e: ft.KeyboardEvent) -> None:
        # Only when main UI is showing and there are multiple files.
        if self.shell.content is not self.root:
            return
        if len(self.items) < 2:
            return
        key = (e.key or "").replace(" ", "").lower()
        idx = self._active_index()
        if key in {"arrowdown", "down"}:
            self._select_index(idx + 1)
        elif key in {"arrowup", "up"}:
            self._select_index(idx - 1)

    def _active(self) -> QueueItem | None:
        for item in self.items:
            if item.id == self.active_id:
                return item
        return self.items[0] if self.items else None

    def _refresh_preview(self) -> None:
        item = self._active()
        if item is None:
            self.preview_body.value = self._tr("no_preview")
            self.preview_md.value = ""
        elif item.status == "converting":
            self.preview_body.value = self._tr("converting")
            self.preview_md.value = ""
        elif item.error:
            self.preview_body.value = f"{self._tr('convert_failed')}: {item.error}"
            self.preview_md.value = ""
        elif not item.markdown:
            self.preview_body.value = self._tr("no_preview")
            self.preview_md.value = ""
        else:
            self.preview_body.value = item.markdown
            self.preview_md.value = item.markdown

        if self.preview_mode == "source":
            self.preview_stack.controls = [self.preview_body]
        else:
            self.preview_stack.controls = [self.preview_md]

    def _set_preview_mode(self, mode: str) -> None:
        self.preview_mode = mode
        self._refresh_preview()
        self.page.update()

    def _on_format_change(self, e: ft.Event[ft.Dropdown]) -> None:
        self.export_format = e.control.value or "md"

    def _convert_items(self, items: list[QueueItem]) -> None:
        self.busy = True
        try:
            for item in items:
                item.status = "converting"
                item.error = None
                self._ui_refresh()
                outcome = converter.convert_file(item.path)
                if outcome.ok:
                    item.status = "done"
                    item.markdown = outcome.markdown
                    item.error = None
                else:
                    item.status = "error"
                    item.error = outcome.error
                self.active_id = item.id
                self._ui_refresh()
        finally:
            self.busy = False
            self._ui_refresh()

    def _ui_refresh(self) -> None:
        self._refresh_input_zone()
        self._refresh_preview()
        self.page.update()

    def _convert_targets(self, only_selected: bool) -> None:
        targets = [i for i in self.items if (i.selected if only_selected else True)]
        if not targets:
            return
        self.page.run_thread(self._convert_items, targets)

    def _toast_export(self, result: export_service.ExportResult) -> None:
        key = "exported_renamed" if result.renamed else "exported"
        self.snack(self._tr(key, path=result.path))

    def _export_one(self) -> None:
        item = self._active()
        if not item or not item.markdown:
            return
        try:
            result = export_service.export_with_format(
                self.settings,
                item.path,
                item.markdown,
                self.export_format,
            )
            self._toast_export(result)
        except Exception as exc:  # noqa: BLE001
            self.snack(self._tr("export_failed", error=str(exc)))

    def _export_all(self) -> None:
        done = [i for i in self.items if i.status == "done" and i.markdown]
        if not done:
            return
        try:
            last = None
            for item in done:
                last = export_service.export_with_format(
                    self.settings,
                    item.path,
                    item.markdown or "",
                    "md",
                )
            if last:
                self._toast_export(last)
        except Exception as exc:  # noqa: BLE001
            self.snack(self._tr("export_failed", error=str(exc)))

    def _clear(self) -> None:
        self.items.clear()
        self.active_id = None
        self._refresh_input_zone()
        self._refresh_preview()
        self.page.update()

    def _open_settings(self, _e: ft.ControlEvent | None = None) -> None:
        def on_changed(settings: AppSettings) -> None:
            self.settings = settings
            self.colors = apply_theme(self.page, settings.theme)
            self._apply_chrome()
            self._retranslate()
            self._refresh_input_zone()
            self._refresh_preview()
            # MCP / float ball already applied inside SettingsPage toggles.
            self.page.update()

        def on_back() -> None:
            self.shell.content = self.root
            self._apply_chrome()
            self._retranslate()
            self._refresh_input_zone()
            self._refresh_preview()
            self.page.update()

        settings_page = SettingsPage(
            self.page,
            self.settings,
            on_back=on_back,
            on_changed=on_changed,
            folder_picker=self.folder_picker,
        )
        self.shell.content = settings_page.root
        self.page.update()
