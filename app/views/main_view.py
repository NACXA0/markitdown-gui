
"""主窗口：文件队列、预览、转换与导出。

负责拖放/选择文件、调用转换引擎、分栏布局以及与设置页切换。
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable
import os
import sys

import flet as ft
import flet_dropzone as ftd

from app import converter, export_service, linux_file_dialog, mcp_server
from app.i18n import t
from app.settings import AppSettings, save_settings, suggested_save_dir
from app.theme import apply_theme, scheme_is_dark, u
from app.views.float_ball import ensure_float_ball
from app.views.settings_view import SettingsPage

# 标签、填充色、圆角系数、图标
_TYPE_BADGES: dict[str, tuple[str, str, float, str]] = {
    ".pdf": ("PDF", "#C44536", 0.7, ft.Icons.PICTURE_AS_PDF),
    ".doc": ("DOC", "#2B579A", 1.2, ft.Icons.DESCRIPTION),
    ".docx": ("DOC", "#2B579A", 1.2, ft.Icons.DESCRIPTION),
    ".ppt": ("PPT", "#C43E1C", 0.9, ft.Icons.SLIDESHOW),
    ".pptx": ("PPT", "#C43E1C", 0.9, ft.Icons.SLIDESHOW),
    ".xls": ("XLS", "#217346", 0.35, ft.Icons.TABLE_CHART),
    ".xlsx": ("XLS", "#217346", 0.35, ft.Icons.TABLE_CHART),
    ".csv": ("CSV", "#1B7A4E", 0.35, ft.Icons.GRID_ON),
    ".png": ("IMG", "#6B3FA0", 2.25, ft.Icons.IMAGE),
    ".jpg": ("IMG", "#6B3FA0", 2.25, ft.Icons.IMAGE),
    ".jpeg": ("IMG", "#6B3FA0", 2.25, ft.Icons.IMAGE),
    ".webp": ("IMG", "#6B3FA0", 2.25, ft.Icons.IMAGE),
    ".gif": ("IMG", "#6B3FA0", 2.25, ft.Icons.GIF_BOX),
    ".svg": ("IMG", "#6B3FA0", 2.25, ft.Icons.IMAGE),
    ".html": ("WEB", "#0E7C7B", 0.5, ft.Icons.LANGUAGE),
    ".htm": ("WEB", "#0E7C7B", 0.5, ft.Icons.LANGUAGE),
    ".md": ("MD", "#0F6B4C", 1.5, ft.Icons.ARTICLE),
    ".txt": ("TXT", "#5A675F", 0.25, ft.Icons.NOTES),
    ".zip": ("ZIP", "#9A6B16", 1.8, ft.Icons.FOLDER_ZIP),
    ".epub": ("BOOK", "#8B5E3C", 2.0, ft.Icons.MENU_BOOK),
    ".mp3": ("AUD", "#B83280", 2.0, ft.Icons.AUDIO_FILE),
    ".wav": ("AUD", "#B83280", 2.0, ft.Icons.AUDIO_FILE),
    ".m4a": ("AUD", "#B83280", 2.0, ft.Icons.AUDIO_FILE),
    ".mp4": ("VID", "#1D4E89", 0.85, ft.Icons.VIDEO_FILE),
    ".mov": ("VID", "#1D4E89", 0.85, ft.Icons.VIDEO_FILE),
}


def _btn_label(control: ft.Control, label: str) -> None:
    """Flet 0.86+ 的按钮用 `content` 属性，而不是 `text`。
    :param control: 按钮控件
    :param label: 显示文字
    :return: None
    """
    control.content = label


def _disabled_colors(scheme: str) -> tuple[str, str]:
    """禁用态前景/背景色。
    :param scheme: 当前配色 id
    :return: (前景色, 背景色)
    """
    if scheme_is_dark(scheme):
        return "#6E6E74", "#2A2A30"
    return "#8A8A86", "#D8D8D4"


def _filled_button_style(colors: dict[str, str], scheme: str) -> ft.ButtonStyle:
    """实心按钮样式（含禁用态）。
    :param colors: 语义色表
    :param scheme: 配色 id
    :return: Flet ButtonStyle
    """
    disabled_fg, disabled_bg = _disabled_colors(scheme)
    return ft.ButtonStyle(
        bgcolor={
            ft.ControlState.DEFAULT: colors["accent"],
            ft.ControlState.DISABLED: disabled_bg,
        },
        color={
            ft.ControlState.DEFAULT: colors["on_accent"],
            ft.ControlState.DISABLED: disabled_fg,
        },
        overlay_color={
            ft.ControlState.HOVERED: colors["accent_soft"],
            ft.ControlState.DISABLED: "transparent",
        },
        icon_color={
            ft.ControlState.DEFAULT: colors["on_accent"],
            ft.ControlState.DISABLED: disabled_fg,
        },
    )


def _outlined_button_style(colors: dict[str, str], scheme: str) -> ft.ButtonStyle:
    """描边按钮样式（含禁用态）。
    :param colors: 语义色表
    :param scheme: 配色 id
    :return: Flet ButtonStyle
    """
    disabled_fg, disabled_bg = _disabled_colors(scheme)
    return ft.ButtonStyle(
        bgcolor={
            ft.ControlState.DEFAULT: colors["surface"],
            ft.ControlState.DISABLED: disabled_bg,
        },
        color={
            ft.ControlState.DEFAULT: colors["ink"],
            ft.ControlState.DISABLED: disabled_fg,
        },
        icon_color={
            ft.ControlState.DEFAULT: colors["ink"],
            ft.ControlState.DISABLED: disabled_fg,
        },
        side={
            ft.ControlState.DEFAULT: ft.BorderSide(1, colors["line"]),
            ft.ControlState.DISABLED: ft.BorderSide(1, disabled_fg),
        },
        overlay_color={
            ft.ControlState.HOVERED: colors["accent_soft"],
            ft.ControlState.DISABLED: "transparent",
        },
    )


def _use_native_dropzone() -> bool:
    """是否启用原生 Dropzone 控件。

    官方 ``python main.py`` 客户端没有 flet_dropzone；可用环境变量覆盖。

    :return: 应使用 Dropzone 则为 True
    """
    flag = os.environ.get("MARKITDOWN_DROPZONE", "").strip().lower()
    if flag in {"1", "true", "yes", "on"}:
        return True
    if flag in {"0", "false", "no", "off"}:
        return False
    if os.environ.get("APPIMAGE"):
        return True
    if getattr(sys, "frozen", False):
        return True
    return Path(sys.argv[0]).name not in {"main.py", "main"}


def _format_size(num: int) -> str:
    """把字节数格式化为可读大小。
    :param num: 文件大小（字节）
    :return: 如 ``12.3 KB``
    """
    size = float(max(0, num))
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if size < 1024 or unit == "TB":
            if unit == "B":
                return f"{int(size)} B"
            text = f"{size:.1f}".rstrip("0").rstrip(".")
            return f"{text} {unit}"
        size /= 1024
    return f"{int(num)} B"


def _count_stats(text: str) -> tuple[int, int]:
    """统计非空白字符数与行数。
    :param text: Markdown 或普通文本
    :return: (字符数, 行数)
    """
    if not text:
        return 0, 0
    chars = sum(1 for c in text if not c.isspace())
    lines = text.count("\n") + (0 if text.endswith("\n") else 1)
    return chars, lines


def _file_kind(name: str) -> tuple[str, str, float, str]:
    """按扩展名取类型徽章信息。
    :param name: 文件名
    :return: (短标签, 填充色, 圆角密度, 图标名)
    """
    ext = Path(name).suffix.lower()
    return _TYPE_BADGES.get(
        ext, ("FILE", "#5A675F", 1.0, ft.Icons.INSERT_DRIVE_FILE)
    )


@dataclass
class QueueItem:
    """队列中的一个源文件及其转换状态。
    :param path: 源路径
    :param name: 显示用文件名
    :param size_bytes: 文件大小
    :param status: pending / converting / done / error
    :param markdown: 转换成功后的正文
    :param error: 失败信息
    :param id: 列表项稳定 id
    """
    path: str
    name: str
    size_bytes: int = 0
    status: str = "pending"
    markdown: str | None = None
    error: str | None = None
    id: str = field(default_factory=lambda: "")

    def __post_init__(self) -> None:
        """若未指定 id，则用路径与对象身份生成。

        :return: None
        """
        if not self.id:
            self.id = f"{self.path}-{id(self)}"


class MainApp:
    """主工作区控制器：构建控件树并处理转换/导出交互。"""

    def __init__(self, page: ft.Page) -> None:
        """创建主界面并挂到页面。

        :param page: Flet 页面
        :return: None
        """
        self.page = page
        self.settings = AppSettings()
        self.items: list[QueueItem] = []
        self.active_id: str | None = None
        self.busy = False
        self.preview_mode = "rendered"
        self.export_format = "md"
        self.dragging = False
        self.layout_mode = "split"
        self.split_ratio = 0.36
        self.auto_save_dir: str | None = None
        self.colors = apply_theme(page, "sage")

        self.file_picker = ft.FilePicker(on_result=self._on_files_picked)
        self.folder_picker = ft.FilePicker()
        self.clipboard = ft.Clipboard()
        page.services.extend(
            [self.file_picker, self.folder_picker, self.clipboard]
        )
        page.padding = 0
        page.spacing = 0
        page.on_keyboard_event = self._on_keyboard
        page.on_resize = self._on_page_resize

        self.wordmark = ft.Text(
            "", theme_style=ft.TextThemeStyle.TITLE_SMALL, weight=ft.FontWeight.W_500
        )
        self.preview_placeholder = ft.Text(
            "",
            theme_style=ft.TextThemeStyle.BODY_MEDIUM,
            text_align=ft.TextAlign.CENTER,
        )
        self.preview_stats = ft.Text(
            "", theme_style=ft.TextThemeStyle.BODY_SMALL
        )

        self.preview_body = ft.TextField(
            multiline=True,
            min_lines=8,
            read_only=True,
            expand=True,
            border=ft.NoInputBorder(),
            filled=True,
            content_padding=0,
        )
        self.preview_md = ft.Markdown(
            "",
            selectable=True,
            extension_set=ft.MarkdownExtensionSet.GITHUB_WEB,
            expand=True,
        )
        self.preview_stack = ft.Column(
            [self.preview_md], expand=True, scroll=ft.ScrollMode.AUTO
        )

        self.btn_add = ft.Button("", icon=ft.Icons.ADD, tooltip="")
        self.btn_clear = ft.OutlinedButton(
            "", icon=ft.Icons.DELETE_OUTLINE, on_click=lambda e: self._clear(), tooltip=""
        )
        self.btn_convert = ft.Button(
            "", icon=ft.Icons.PLAY_ARROW, on_click=lambda e: self._convert_needed(), tooltip=""
        )
        self.btn_settings = ft.OutlinedButton(
            "", icon=ft.Icons.SETTINGS_OUTLINED, on_click=self._open_settings, tooltip=""
        )
        self.btn_copy = ft.OutlinedButton(
            "", icon=ft.Icons.CONTENT_COPY, on_click=self._on_copy_click, tooltip=""
        )
        self.btn_choose = ft.Button("", icon=ft.Icons.FOLDER_OPEN)
        self.btn_preview_mode = ft.OutlinedButton(
            "", icon=ft.Icons.CODE, on_click=self._toggle_preview_mode, tooltip=""
        )
        self.btn_export_one = ft.OutlinedButton(
            "", icon=ft.Icons.IOS_SHARE, on_click=self._on_export_one, tooltip=""
        )
        self.btn_export_all = ft.OutlinedButton(
            "", icon=ft.Icons.FOLDER_ZIP, on_click=self._on_export_all, tooltip=""
        )
        self._sync_pick_action()

        self.tab_files_label = ft.Text("")
        self.tab_split_label = ft.Text("")
        self.tab_preview_label = ft.Text("")
        self.layout_tabs = ft.SegmentedButton(
            show_selected_icon=False,
            selected=["split"],
            segments=[
                ft.Segment(value="files", label=self.tab_files_label),
                ft.Segment(value="split", label=self.tab_split_label),
                ft.Segment(value="preview", label=self.tab_preview_label),
            ],
            on_change=self._on_layout_change,
        )

        self.empty_drop_icon = ft.Icon(ft.Icons.DESCRIPTION_OUTLINED)
        self.empty_drop_title = ft.Text(
            "",
            theme_style=ft.TextThemeStyle.TITLE_LARGE,
            weight=ft.FontWeight.W_500,
            text_align=ft.TextAlign.CENTER,
        )
        self.empty_drop_hint = ft.Text(
            "",
            theme_style=ft.TextThemeStyle.BODY_MEDIUM,
            text_align=ft.TextAlign.CENTER,
        )
        self.empty_drop_col = ft.Column(
            [
                self.empty_drop_icon,
                self.empty_drop_title,
                self.empty_drop_hint,
                self.btn_choose,
            ],
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            spacing=u(1.5),
            tight=True,
        )
        self.file_list = ft.Column(spacing=u(0.5), expand=True, scroll=ft.ScrollMode.AUTO)
        self.progress_bar = ft.ProgressBar(
            value=0,
            bar_height=4,
            expand=True,
            border_radius=u(0.5),
        )
        self.progress_label = ft.Text(
            "", theme_style=ft.TextThemeStyle.BODY_SMALL
        )
        self.progress_row = ft.Row(
            [self.progress_bar, self.progress_label],
            spacing=u(1),
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
            opacity=0,
            animate_opacity=180,
        )
        self.progress_slot = ft.Container(
            content=self.progress_row,
            height=u(3.5),
            padding=ft.Padding.symmetric(horizontal=u(1.25)),
            alignment=ft.Alignment.CENTER,
        )
        self.files_col = ft.Column(
            [self.progress_slot, self.file_list],
            expand=True,
            spacing=u(1),
            visible=False,
        )
        self.empty_layer = ft.Container(
            content=self.empty_drop_col,
            alignment=ft.Alignment.CENTER,
            expand=True,
        )
        self.file_stage = ft.Container(
            content=ft.Stack(
                [self.files_col, self.empty_layer],
                expand=True,
                fit=ft.StackFit.EXPAND,
            ),
            padding=u(2),
            border_radius=u(2),
            alignment=ft.Alignment.CENTER,
            expand=True,
        )
        if _use_native_dropzone():
            self.file_pane = ftd.Dropzone(
                content=self.file_stage,
                expand=True,
                on_dropped=self._on_dropped,
                on_entered=self._on_drag_entered,
                on_exited=self._on_drag_exited,
            )
        else:
            self.file_pane = self.file_stage
        self.preview_panel = ft.Container(
            content=ft.Column(
                [self.preview_stack, self.preview_stats],
                expand=True,
                spacing=u(1),
            ),
            padding=ft.Padding.symmetric(horizontal=u(4), vertical=u(3)),
            border_radius=u(2),
        )
        self.split_bar = ft.Container(
            width=2,
            bgcolor=None,
            border_radius=1,
            expand=True,
        )
        self.splitter = ft.GestureDetector(
            mouse_cursor=ft.MouseCursor.RESIZE_LEFT_RIGHT,
            drag_interval=16,
            on_horizontal_drag_update=self._on_split_drag,
            content=ft.Container(
                width=u(1.5),
                alignment=ft.Alignment.CENTER,
                content=self.split_bar,
            ),
        )

        self.body_row = ft.Row(
            [self.file_pane, self.splitter, self.preview_panel],
            expand=True,
            spacing=0,
            vertical_alignment=ft.CrossAxisAlignment.STRETCH,
        )

        self.left_actions = ft.Row(
            [self.btn_add, self.btn_clear, self.btn_convert],
            spacing=u(1),
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        )
        self.right_actions = ft.Row(
            [
                self.btn_preview_mode,
                self.btn_copy,
                self.btn_export_one,
                self.btn_export_all,
                self.btn_settings,
            ],
            spacing=u(1),
            wrap=False,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        )
        self.topbar = ft.Row(
            [
                self.left_actions,
                ft.Container(expand=True),
                self.layout_tabs,
                ft.Container(width=u(1)),
                self.right_actions,
            ],
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        )

        self.drag_title = ft.Text(
            "",
            theme_style=ft.TextThemeStyle.TITLE_MEDIUM,
            weight=ft.FontWeight.W_500,
            text_align=ft.TextAlign.CENTER,
        )
        self.drag_veil = ft.Container(
            content=self.drag_title,
            alignment=ft.Alignment.CENTER,
            visible=False,
            left=0,
            top=0,
            right=0,
            bottom=0,
            border_radius=u(2),
        )

        self.main_column = ft.Column(
            [self.topbar, self.body_row],
            expand=True,
            spacing=u(1.5),
        )
        self.root = ft.Container(
            content=ft.Stack(
                [self.main_column, self.drag_veil],
                expand=True,
            ),
            expand=True,
            border_radius=u(1.5),
            padding=u(2),
        )
        self.workspace = self.root
        self.shell = ft.Container(content=self.workspace, expand=True)
        page.add(self.shell)

    def bootstrap(self, settings: AppSettings) -> None:
        """应用已加载的设置、刷新界面，并按需启动 MCP。

        :param settings: 启动时的用户设置
        :return: None
        """
        self.settings = settings
        self.colors = apply_theme(self.page, settings.color_scheme)
        self._apply_chrome()
        self._retranslate()
        self._refresh_workspace()
        self._refresh_preview()
        if settings.mcp_enabled:
            mcp_server.apply_setting(settings)
        ensure_float_ball(settings.float_ball)

    def _on_page_resize(self, _e: ft.PageResizeEvent | None = None) -> None:
        """窗口尺寸变化时重算分栏宽度。

        :param _e: 缩放事件（可忽略）
        :return: None
        """
        self._apply_split()
        self.page.update()

    def _on_layout_change(self, e: ft.ControlEvent) -> None:
        """切换「文件 / 分栏 / 预览」布局。

        :param e: 分段按钮事件
        :return: None
        """
        selected = list(e.control.selected or ["split"])
        self.layout_mode = selected[0] if selected else "split"
        self._apply_split()
        self._sync_action_states()
        self.page.update()

    def _on_split_drag(self, e: ft.DragUpdateEvent) -> None:
        """拖动中间分隔条调整左右宽度比。

        :param e: 水平拖动事件
        :return: None
        """
        if self.layout_mode != "split":
            return
        dx = 0.0
        if e.primary_delta is not None:
            dx = float(e.primary_delta)
        elif e.global_delta is not None:
            dx = float(e.global_delta.x)
        total = self._body_width()
        if total <= 0:
            return
        self.split_ratio = min(0.72, max(0.22, self.split_ratio + dx / total))
        self._apply_split()
        self.page.update()

    def _body_width(self) -> float:
        """工作区可用宽度（减去外边距）。

        :return: 像素宽度
        """
        width = float(self.page.width or 1100)
        return max(u(40), width - u(4))

    def _apply_split(self) -> None:
        """按 ``layout_mode`` 显示/隐藏左右栏并设置宽度。

        :return: None
        """
        mode = self.layout_mode
        total = self._body_width()
        show_files = mode in {"files", "split"}
        show_preview = mode in {"preview", "split"}
        self.file_pane.visible = show_files
        self.preview_panel.visible = show_preview
        self.splitter.visible = mode == "split"
        if mode == "files":
            self.file_pane.width = None
            self.file_pane.expand = True
            self.preview_panel.width = 0
            self.preview_panel.expand = False
        elif mode == "preview":
            self.file_pane.width = 0
            self.file_pane.expand = False
            self.preview_panel.width = None
            self.preview_panel.expand = True
        else:
            left = total * self.split_ratio
            left = max(u(22), min(left, total - u(36)))
            self.file_pane.width = left
            self.file_pane.expand = False
            self.preview_panel.width = None
            self.preview_panel.expand = True

    def _on_drag_entered(self, _e: ft.ControlEvent | None = None) -> None:
        """文件拖入投放区时高亮。

        :param _e: 拖入事件
        :return: None
        """
        self.dragging = True
        self._style_drag_chrome()
        self.page.update()

    def _on_drag_exited(self, _e: ft.ControlEvent | None = None) -> None:
        """文件拖出投放区时取消高亮。

        :param _e: 拖出事件
        :return: None
        """
        self.dragging = False
        self._style_drag_chrome()
        self.page.update()

    async def _on_dropped(self, e: ftd.DropzoneEvent) -> None:
        """处理 Dropzone 放下的本地文件路径。

        :param e: 含 files 列表的投放事件
        :return: None
        """
        paths: list[str] = []
        for file in e.files or []:
            path = getattr(file, "path", None)
            if path and str(path).startswith("/") and not str(path).startswith("blob:"):
                paths.append(str(path))
        self.dragging = False
        self._style_drag_chrome()
        if paths:
            self.add_paths(paths)
        else:
            self._refresh_workspace()
            self.page.update()

    def _style_drag_chrome(self) -> None:
        """按是否正在拖放更新投放区边框与遮罩。

        :return: None
        """
        c = self.colors
        self.drag_veil.visible = self.dragging and bool(self.items)
        if self.dragging:
            self.file_stage.bgcolor = c["accent_soft"]
            self.file_stage.border = ft.Border.all(2, c["accent"])
        else:
            self._style_file_stage()
        self._sync_drop_copy()

    def _style_file_stage(self) -> None:
        """恢复文件区默认背景与边框。

        :return: None
        """
        c = self.colors
        self.file_stage.bgcolor = c["surface_alt"]
        self.file_stage.border = ft.Border.all(1, c["line"])

    def _tr(self, key: str, **kwargs: Any) -> str:
        """当前语言下的翻译。

        :param key: 文案键
        :param kwargs: 格式化参数
        :return: 翻译字符串
        """
        return t(self.settings.language, key, **kwargs)

    def _markdown_styles(self) -> ft.MarkdownStyleSheet:
        """渲染预览用的 Markdown 样式。

        :return: 与当前配色匹配的样式表
        """
        c = self.colors
        return ft.MarkdownStyleSheet(
            p_text_style=ft.TextStyle(height=1.55, color=c["ink"]),
            h1_text_style=ft.TextStyle(weight=ft.FontWeight.W_600, color=c["ink"]),
            h2_text_style=ft.TextStyle(weight=ft.FontWeight.W_600, color=c["ink"]),
            h3_text_style=ft.TextStyle(weight=ft.FontWeight.W_600, color=c["ink"]),
            code_text_style=ft.TextStyle(color=c["ink"]),
        )

    def _apply_chrome(self) -> None:
        """把当前配色套到顶栏、预览、按钮等控件。

        :return: None
        """
        c = self.colors
        self.page.bgcolor = c["bg"]
        self.wordmark.color = c["accent"]
        self.preview_placeholder.color = c["muted"]
        self.preview_stats.color = c["muted"]
        self.drag_title.color = c["accent_2"]
        self.preview_panel.bgcolor = c["paper"]
        self.preview_panel.shadow = ft.BoxShadow(
            blur_radius=u(3.5),
            color=c["shadow"],
            offset=ft.Offset(0, u(1)),
        )
        self.preview_body.bgcolor = c["paper"]
        self.preview_body.focused_bgcolor = c["paper"]
        self.preview_body.color = c["ink"]
        self.preview_md.md_style_sheet = self._markdown_styles()
        self.empty_drop_title.color = c["ink"]
        self.empty_drop_hint.color = c["muted"]
        self.drag_veil.bgcolor = c["veil"]
        self.split_bar.bgcolor = c["accent"]
        self._sync_mode_button()
        self._style_file_stage()
        self.progress_bar.color = c["accent"]
        self.progress_bar.bgcolor = c["line"]
        self.progress_label.color = c["muted"]
        filled = _filled_button_style(c, self.settings.color_scheme)
        outlined = _outlined_button_style(c, self.settings.color_scheme)
        self.btn_add.style = filled
        self.btn_add.bgcolor = None
        self.btn_add.color = None
        self.btn_convert.style = filled
        self.btn_convert.bgcolor = None
        self.btn_convert.color = None
        self.btn_choose.style = filled
        self.btn_choose.bgcolor = None
        self.btn_choose.color = None
        self.btn_clear.style = outlined
        self.btn_settings.style = outlined
        self.btn_copy.style = outlined
        self.btn_preview_mode.style = outlined
        self.btn_export_one.style = outlined
        self.btn_export_all.style = outlined
        self.layout_tabs.style = ft.ButtonStyle(
            bgcolor={
                ft.ControlState.SELECTED: c["accent"],
                ft.ControlState.DEFAULT: c["surface"],
            },
            color={
                ft.ControlState.SELECTED: c["on_accent"],
                ft.ControlState.DEFAULT: c["ink"],
            },
            overlay_color={
                ft.ControlState.HOVERED: c["accent_soft"],
            },
        )
        self.tab_files_label.color = None
        self.tab_split_label.color = None
        self.tab_preview_label.color = None
        self._sync_action_states()

    def _sync_mode_button(self) -> None:
        """同步源码/渲染切换按钮的图标与文字。

        :return: None
        """
        rendered = self.preview_mode == "rendered"
        self.btn_preview_mode.icon = ft.Icons.CODE if rendered else ft.Icons.MENU_BOOK
        _btn_label(
            self.btn_preview_mode,
            self._tr("source") if rendered else self._tr("rendered"),
        )

    def _sync_drop_copy(self) -> None:
        """更新空状态与拖放遮罩上的提示文案。

        :return: None
        """
        active = self.dragging
        self.empty_drop_title.value = (
            self._tr("drop_active") if active else self._tr("drop_title")
        )
        self.empty_drop_hint.value = self._tr("drop_hint")
        self.drag_title.value = self._tr("drop_active")
        self.empty_drop_icon.color = (
            self.colors["accent"] if active else self.colors["accent_2"]
        )
        self.empty_drop_icon.size = u(5)

    def _retranslate(self) -> None:
        """语言变更后刷新所有可见文案。

        :return: None
        """
        self.page.title = self._tr("app_name")
        self.wordmark.value = self._tr("wordmark")
        _btn_label(self.btn_add, self._tr("add_more"))
        _btn_label(self.btn_clear, self._tr("clear_queue"))
        _btn_label(self.btn_convert, self._tr("convert_all"))
        _btn_label(self.btn_settings, self._tr("settings"))
        _btn_label(self.btn_copy, self._tr("copy_clipboard"))
        _btn_label(self.btn_choose, self._tr("choose_files"))
        _btn_label(self.btn_export_one, self._tr("export_one"))
        _btn_label(self.btn_export_all, self._tr("export_all"))
        self.tab_files_label.value = self._tr("layout_files")
        self.tab_split_label.value = self._tr("layout_split")
        self.tab_preview_label.value = self._tr("layout_preview")
        self._sync_mode_button()
        self._sync_drop_copy()
        self._sync_pick_action()
        self._sync_action_states()

    def snack(self, message: str) -> None:
        """底部短暂提示。

        :param message: 提示文字
        :return: None
        """
        self.page.show_dialog(
            ft.SnackBar(content=ft.Text(message), open=True)
        )

    def _sync_pick_action(self) -> None:
        """把「添加/选择文件」绑定到系统文件选择器。

        :return: None
        """
        action = ft.PickFiles(
            self.file_picker,
            allow_multiple=True,
            dialog_title=self._tr("choose_files"),
            initial_directory=suggested_save_dir(self.settings),
        )
        self.btn_add.action = action
        self.btn_choose.action = action

    def _on_files_picked(self, e: ft.FilePickerResultEvent) -> None:
        """FilePicker 回调：把选中路径加入队列。

        :param e: 选择结果
        :return: None
        """
        files = e.files or []
        paths = [f.path for f in files if getattr(f, "path", None)]
        if paths:
            self.add_paths(paths)

    def _on_browse_click(self, _e: ft.ControlEvent | None = None) -> None:
        """点击浏览时异步打开文件对话框。

        :param _e: 点击事件
        :return: None
        """
        self.page.run_task(self._browse)

    def _on_copy_click(self, _e: ft.ControlEvent | None = None) -> None:
        """复制当前预览文本。

        :param _e: 点击事件
        :return: None
        """
        self.page.run_task(self._copy_preview)

    def _on_export_one(self, _e: ft.ControlEvent | None = None) -> None:
        """弹出单文件导出格式选择。

        :param _e: 点击事件
        :return: None
        """
        if self.btn_export_one.disabled:
            return
        self._show_choice_dialog(
            self._tr("export_as"),
            [
                (ft.Icons.ARTICLE, self._tr("format_md"), self._tr("format_md_hint"), lambda: self._export_as("md")),
                (ft.Icons.DESCRIPTION, self._tr("format_docx"), self._tr("format_docx_hint"), lambda: self._export_as("docx")),
                (ft.Icons.PICTURE_AS_PDF, self._tr("format_pdf"), self._tr("format_pdf_hint"), lambda: self._export_as("pdf")),
                (ft.Icons.LANGUAGE, self._tr("format_html"), self._tr("format_html_hint"), lambda: self._export_as("html")),
            ],
        )

    def _on_export_all(self, _e: ft.ControlEvent | None = None) -> None:
        """弹出批量导出（文件夹或 ZIP）选择。

        :param _e: 点击事件
        :return: None
        """
        if self.btn_export_all.disabled:
            return
        self._show_choice_dialog(
            self._tr("export_all"),
            [
                (
                    ft.Icons.FOLDER_OPEN,
                    self._tr("export_to_folder"),
                    self._tr("export_to_folder_hint"),
                    lambda: self.page.run_task(self._export_all),
                ),
                (
                    ft.Icons.FOLDER_ZIP,
                    self._tr("export_zip"),
                    self._tr("export_zip_hint"),
                    lambda: self.page.run_task(self._export_zip),
                ),
            ],
        )

    def _show_choice_dialog(
        self,
        title: str,
        choices: list[tuple[str, str, str, Callable[[], None]]],
    ) -> None:
        c = self.colors

        def close_and_run(action: Callable[[], None]) -> None:
            """关闭对话框后执行所选动作。

            :param action: 无参回调
            :return: None
            """
            self.page.pop_dialog()
            action()

        tiles = [
            ft.ListTile(
                leading=ft.Icon(icon, color=c["accent"]),
                title=ft.Text(label, weight=ft.FontWeight.W_600, color=c["ink"]),
                subtitle=ft.Text(hint, color=c["muted"]),
                trailing=ft.Icon(ft.Icons.CHEVRON_RIGHT, color=c["muted"]),
                bgcolor=c["paper"],
                shape=ft.RoundedRectangleBorder(radius=u(1)),
                on_click=lambda _e, fn=action: close_and_run(fn),
            )
            for icon, label, hint, action in choices
        ]
        self.page.show_dialog(
            ft.AlertDialog(
                modal=False,
                bgcolor=c["surface"],
                shape=ft.RoundedRectangleBorder(radius=u(2)),
                title=ft.Text(title, weight=ft.FontWeight.W_700, color=c["ink"]),
                content=ft.Column(tiles, tight=True, spacing=u(0.5), width=u(42)),
                actions=[
                    ft.TextButton(
                        self._tr("close"),
                        on_click=lambda _e: self.page.pop_dialog(),
                    )
                ],
                actions_alignment=ft.MainAxisAlignment.END,
            )
        )

    async def _browse(self) -> None:
        """打开文件选择器并把结果加入队列。

        :return: None
        """
        title = self._tr("choose_files")
        initial = suggested_save_dir(self.settings)
        paths: list[str] | None = None
        try:
            if sys.platform.startswith("linux"):
                try:
                    paths = await linux_file_dialog.pick_files(
                        title=title,
                        allow_multiple=True,
                        initial_directory=initial,
                    )
                except linux_file_dialog.DialogUnavailable:
                    paths = None
            if paths is None:
                files = await self.file_picker.pick_files(
                    dialog_title=title,
                    allow_multiple=True,
                    initial_directory=initial,
                )
                paths = [f.path for f in files if getattr(f, "path", None)]
        except Exception as exc:  # noqa: BLE001
            self.snack(self._tr("picker_failed", error=str(exc)))
            return
        if paths:
            self.add_paths(paths)

    async def _copy_preview(self) -> None:
        """把当前预览 Markdown 写入剪贴板。

        :return: None
        """
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
        """去重加入队列，并按转换模式决定是否立即转换。

        :param paths: 源文件路径列表
        :return: None
        """
        existing = {i.path for i in self.items}
        added: list[QueueItem] = []
        for path in paths:
            if not path or path in existing:
                continue
            size = 0
            try:
                size = Path(path).stat().st_size
            except OSError:
                size = 0
            item = QueueItem(path=path, name=Path(path).name, size_bytes=size)
            self.items.append(item)
            added.append(item)
            existing.add(path)
        if not added:
            self._refresh_workspace()
            self.page.update()
            return

        self.active_id = added[0].id
        self._refresh_workspace()
        self._refresh_preview()

        should_convert = len(self.items) == 1 or self.settings.convert_mode in {
            "drop_immediate",
            "single_immediate_multi_list",
        }
        if should_convert:
            self.page.run_task(self._start_convert, added)
        self.page.update()

    def _status_label(self, item: QueueItem) -> tuple[str | None, str]:
        """列表项状态文字与颜色。

        :param item: 队列项
        :return: (状态文案或 None, 颜色)
        """
        if item.status == "pending":
            return None, self.colors["muted"]
        if item.status == "converting":
            return self._tr("status_converting"), self.colors["muted"]
        if item.status == "done":
            return None, self.colors["accent"]
        if item.status == "error":
            text = self._tr("status_error")
            if item.error:
                text = item.error
            return text, self.colors["danger"]
        return None, self.colors["muted"]

    def _remove_item(self, item_id: str) -> None:
        """从队列移除一项并刷新界面。

        :param item_id: 队列项 id
        :return: None
        """
        self.items = [i for i in self.items if i.id != item_id]
        if self.active_id == item_id:
            self.active_id = self.items[0].id if self.items else None
        self._refresh_workspace()
        self._refresh_preview()
        self.page.update()

    def _make_remove(self, item_id: str) -> Callable[[ft.ControlEvent], None]:
        """生成「移除」按钮回调。

        :param item_id: 要删除的项 id
        :return: 点击处理函数
        """
        def _remove(_e: ft.ControlEvent) -> None:
            """执行移除。

            :param _e: 点击事件
            :return: None
            """
            self._remove_item(item_id)

        return _remove

    def _make_select(self, item_id: str) -> Callable[[ft.ControlEvent], None]:
        """生成选中列表项的回调。

        :param item_id: 要选中的项 id
        :return: 点击处理函数
        """
        def _select(_e: ft.ControlEvent) -> None:
            """设为当前预览项。

            :param _e: 点击事件
            :return: None
            """
            self.active_id = item_id
            self._refresh_workspace()
            self._refresh_preview()
            self.page.update()

        return _select

    def _type_badge(self, name: str) -> ft.Control:
        """文件类型色块图标。

        :param name: 文件名
        :return: 圆形/圆角色块控件
        """
        _label, fill, radius_u, icon = _file_kind(name)
        side = u(4.5)
        return ft.Container(
            content=ft.Icon(icon, color="#FFFFFF", size=u(2.25)),
            width=side,
            height=side,
            bgcolor=fill,
            border_radius=u(radius_u),
            alignment=ft.Alignment.CENTER,
        )

    def _item_leading(self, item: QueueItem) -> ft.Control:
        """列表项左侧：转换中为进度环，否则为类型徽章。

        :param item: 队列项
        :return: 前导控件
        """
        side = u(4.5)
        if item.status == "converting":
            return ft.Container(
                content=ft.ProgressRing(
                    width=u(2.5),
                    height=u(2.5),
                    stroke_width=2,
                    color=self.colors["accent"],
                    bgcolor=self.colors["line"],
                    value=None,
                ),
                width=side,
                height=side,
                alignment=ft.Alignment.CENTER,
            )
        return self._type_badge(item.name)

    def _rail_row_for(self, item: QueueItem) -> ft.Control:
        """构建单行文件列表项。

        :param item: 队列项
        :return: 可点击的行容器
        """
        status, color = self._status_label(item)
        active = item.id == self.active_id
        name_color = self.colors["ink"] if active else self.colors["muted"]
        meta = _format_size(item.size_bytes)
        if status:
            meta = f"{meta} · {status}"
        texts = [
            ft.Text(
                item.name,
                theme_style=ft.TextThemeStyle.TITLE_SMALL,
                weight=ft.FontWeight.W_500 if active else ft.FontWeight.W_400,
                color=name_color,
                no_wrap=False,
                max_lines=None,
                overflow=ft.TextOverflow.VISIBLE,
            ),
            ft.Text(
                meta,
                theme_style=ft.TextThemeStyle.BODY_SMALL,
                color=color if status else self.colors["muted"],
            ),
        ]
        return ft.Container(
            content=ft.Row(
                [
                    self._item_leading(item),
                    ft.Column(texts, spacing=u(0.25), expand=True, tight=True),
                    ft.OutlinedButton(
                        self._tr("remove_file"),
                        icon=ft.Icons.CLOSE,
                        on_click=self._make_remove(item.id),
                    ),
                ],
                vertical_alignment=ft.CrossAxisAlignment.START,
            ),
            padding=ft.Padding.symmetric(horizontal=u(1.25), vertical=u(1)),
            border_radius=u(1.25),
            bgcolor=self.colors["accent_soft"] if active else None,
            on_click=self._make_select(item.id),
        )

    def _refresh_progress(self) -> None:
        """更新顶部转换进度条与计数。

        :return: None
        """
        total = len(self.items)
        done = sum(1 for i in self.items if i.status == "done")
        processed = sum(1 for i in self.items if i.status in {"done", "error"})
        in_progress = bool(total) and (
            self.busy or any(i.status == "converting" for i in self.items)
        )
        self.progress_row.opacity = 1 if in_progress else 0
        self.progress_bar.value = (processed / total) if total else 0
        self.progress_label.value = self._tr(
            "convert_progress", done=done, total=total
        )

    def _refresh_file_list(self) -> None:
        """重建文件列表控件。

        :return: None
        """
        self.file_list.controls = [self._rail_row_for(i) for i in self.items]
        self._refresh_progress()

    def _has_previewable(self) -> bool:
        """当前选中项是否已有 Markdown。

        :return: 可预览则为 True
        """
        item = self._active()
        return bool(item and item.markdown)

    def _sync_action_states(self) -> None:
        """按布局与队列状态启用/禁用工具栏按钮。

        :return: None
        """
        files_visible = self.layout_mode in {"files", "split"}
        preview_visible = self.layout_mode in {"preview", "split"}
        has_files = bool(self.items)
        previewable = self._has_previewable()
        needs_convert = any(i.status in {"pending", "error"} for i in self.items)
        done_count = sum(1 for i in self.items if i.status == "done" and i.markdown)

        self.btn_add.disabled = not files_visible
        self.btn_add.tooltip = (
            self._tr("tip_add") if files_visible else self._tr("tip_add_layout")
        )

        if not files_visible:
            self.btn_clear.disabled = True
            self.btn_clear.tooltip = self._tr("tip_clear_layout")
        elif not has_files:
            self.btn_clear.disabled = True
            self.btn_clear.tooltip = self._tr("tip_clear_empty")
        else:
            self.btn_clear.disabled = False
            self.btn_clear.tooltip = self._tr("tip_clear")

        if not files_visible:
            self.btn_convert.disabled = True
            self.btn_convert.tooltip = self._tr("tip_convert_layout")
        elif self.busy:
            self.btn_convert.disabled = True
            self.btn_convert.tooltip = self._tr("tip_convert_busy")
        elif not needs_convert:
            self.btn_convert.disabled = True
            self.btn_convert.tooltip = self._tr("tip_convert_none")
        else:
            self.btn_convert.disabled = False
            self.btn_convert.tooltip = self._tr("tip_convert")

        preview_ok = preview_visible and previewable
        if not preview_visible:
            preview_tip = self._tr("tip_preview_layout")
        elif not previewable:
            preview_tip = self._tr("tip_preview_need")
        else:
            preview_tip = ""
        self.btn_preview_mode.disabled = not preview_ok
        self.btn_preview_mode.tooltip = preview_tip or self._tr("tip_preview_mode")
        self.btn_copy.disabled = not preview_ok
        self.btn_copy.tooltip = preview_tip or self._tr("tip_copy")
        self.btn_export_one.disabled = not preview_ok
        self.btn_export_one.tooltip = preview_tip or self._tr("tip_export")

        if done_count < 2:
            self.btn_export_all.disabled = True
            self.btn_export_all.tooltip = self._tr("tip_export_all_need")
        else:
            self.btn_export_all.disabled = False
            self.btn_export_all.tooltip = self._tr("tip_export_all")
        self.btn_settings.tooltip = self._tr("tip_settings")

    def _refresh_workspace(self) -> None:
        """刷新空状态、列表、分栏与按钮状态。

        :return: None
        """
        has_files = bool(self.items)
        self._sync_action_states()
        self.files_col.visible = has_files
        self.empty_layer.visible = not has_files
        self.file_stage.alignment = (
            ft.Alignment.TOP_LEFT if has_files else ft.Alignment.CENTER
        )
        if has_files:
            self._refresh_file_list()
        else:
            self.progress_row.opacity = 0
            self.file_list.controls.clear()
        self._apply_split()
        self._style_drag_chrome()
        self._sync_mode_button()

    def _active_index(self) -> int:
        """当前选中项在列表中的下标。

        :return: 下标；空队列为 -1
        """
        if not self.items:
            return -1
        for i, item in enumerate(self.items):
            if item.id == self.active_id:
                return i
        return 0

    def _select_index(self, index: int) -> None:
        """按索引选中队列项并刷新预览。

        :param index: 目标下标（会被夹紧到合法范围）
        :return: None
        """
        if not self.items:
            return
        index = max(0, min(index, len(self.items) - 1))
        self.active_id = self.items[index].id
        self._refresh_workspace()
        self._refresh_preview()
        self.page.update()

    def _on_keyboard(self, e: ft.KeyboardEvent) -> None:
        """方向键在文件列表中上下移动选中项。

        :param e: 键盘事件
        :return: None
        """
        if self.shell.content is not self.workspace:
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
        """当前预览对应的队列项。

        :return: 选中项；否则第一项或 None
        """
        for item in self.items:
            if item.id == self.active_id:
                return item
        return self.items[0] if self.items else None

    def _set_preview_stats(self, text: str | None) -> None:
        """更新预览区字数/行数标签。

        :param text: 当前正文；空则隐藏统计
        :return: None
        """
        chars, lines = _count_stats(text or "")
        self.preview_stats.value = self._tr("preview_stats", chars=chars, lines=lines)
        self.preview_stats.visible = bool(text)

    def _show_placeholder(self, message: str) -> None:
        """在预览区显示居中提示而非正文。

        :param message: 提示文字
        :return: None
        """
        self.preview_placeholder.value = message
        self.preview_stack.controls = [
            ft.Container(
                content=self.preview_placeholder,
                alignment=ft.Alignment.CENTER,
                expand=True,
            )
        ]
        self._set_preview_stats(None)

    def _refresh_preview(self) -> None:
        """按当前项状态刷新源码或渲染预览。

        :return: None
        """
        item = self._active()
        if item is None:
            self._show_placeholder(self._tr("no_preview"))
            return
        if item.status == "converting":
            self._show_placeholder(self._tr("converting"))
            return
        if item.error:
            self._show_placeholder(
                f"{self._tr('convert_failed')}: {item.error}"
            )
            return
        if not item.markdown:
            self._show_placeholder(self._tr("no_preview"))
            return

        self.preview_body.value = item.markdown
        self.preview_md.value = item.markdown
        self._set_preview_stats(item.markdown)
        if self.preview_mode == "source":
            self.preview_stack.controls = [self.preview_body]
        else:
            self.preview_stack.controls = [self.preview_md]

    def _toggle_preview_mode(self, _e: ft.ControlEvent | None = None) -> None:
        """在源码与渲染预览之间切换。

        :param _e: 点击事件
        :return: None
        """
        self.preview_mode = "source" if self.preview_mode == "rendered" else "rendered"
        self._sync_mode_button()
        self._refresh_preview()
        self.page.update()

    def _export_as(self, fmt: str) -> None:
        """记住导出格式并启动单文件另存为。

        :param fmt: md / docx / pdf / html
        :return: None
        """
        self.export_format = fmt
        self.page.run_task(self._export_one)

    async def _start_convert(self, items: list[QueueItem]) -> None:
        """多文件时先选保存目录，再在后台线程转换。

        :param items: 待转换队列项
        :return: None
        """
        if self.busy or not items:
            return
        dest = None
        if len(items) >= 2:
            dest = await self._pick_export_dir("choose_batch_save")
            if dest:
                self._remember_export_dir(dest)
        self.auto_save_dir = dest
        self.page.run_thread(self._convert_items, items)

    def _convert_items(self, items: list[QueueItem]) -> None:
        """同步转换一批文件，可选自动写入目录。

        :param items: 待转换项
        :return: None
        """
        self.busy = True
        auto_dir = self.auto_save_dir
        saved = 0
        save_error: str | None = None
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
                    if auto_dir and item.markdown:
                        try:
                            export_service.export_markdown(
                                self.settings,
                                item.path,
                                item.markdown,
                                save_dir=auto_dir,
                            )
                            saved += 1
                        except Exception as exc:  # noqa: BLE001
                            save_error = str(exc)
                else:
                    item.status = "error"
                    item.error = outcome.error
                self.active_id = item.id
                self._ui_refresh()
        finally:
            self.auto_save_dir = None
            self.busy = False
            self._ui_refresh()
            if save_error:
                self.snack(self._tr("export_failed", error=save_error))
            elif auto_dir and saved:
                self.snack(self._tr("auto_saved", path=auto_dir))

    def _ui_refresh(self) -> None:
        """从工作线程安全刷新工作区与预览。

        :return: None
        """
        self._refresh_workspace()
        self._refresh_preview()
        self.page.update()

    def _convert_needed(self) -> None:
        """转换所有 pending/error 项。

        :return: None
        """
        targets = [i for i in self.items if i.status in {"pending", "error"}]
        if not targets:
            return
        self.page.run_task(self._start_convert, targets)

    def _remember_export_dir(self, directory: str) -> None:
        """把最近导出目录写入设置。

        :param directory: 文件夹路径
        :return: None
        """
        directory = str(Path(directory).expanduser())
        if self.settings.default_save_dir == directory:
            return
        self.settings.default_save_dir = directory
        save_settings(self.settings)

    async def _pick_save_path(self, default_name: str) -> str | None:
        """弹出另存为对话框。

        :param default_name: 建议文件名
        :return: 路径；取消或失败为 None
        """
        initial = suggested_save_dir(self.settings)
        title = self._tr("save_file")
        ext = Path(default_name).suffix.lstrip(".")
        try:
            if sys.platform.startswith("linux"):
                try:
                    dest = await linux_file_dialog.save_file(
                        title=title,
                        default_name=default_name,
                        initial_directory=initial,
                    )
                    return dest
                except linux_file_dialog.DialogUnavailable:
                    pass
            return await self.file_picker.save_file(
                dialog_title=title,
                file_name=default_name,
                initial_directory=initial,
                file_type=ft.FilePickerFileType.CUSTOM if ext else ft.FilePickerFileType.ANY,
                allowed_extensions=[ext] if ext else None,
            )
        except Exception as exc:  # noqa: BLE001
            self.snack(self._tr("picker_failed", error=str(exc)))
            return None

    async def _pick_export_dir(self, title_key: str = "choose_export_folder") -> str | None:
        """弹出文件夹选择框。

        :param title_key: i18n 标题键
        :return: 目录路径；取消或失败为 None
        """
        title = self._tr(title_key)
        initial = suggested_save_dir(self.settings)
        try:
            if sys.platform.startswith("linux"):
                try:
                    return await linux_file_dialog.pick_directory(
                        title=title, initial_directory=initial
                    )
                except linux_file_dialog.DialogUnavailable:
                    pass
            return await self.folder_picker.get_directory_path(
                dialog_title=title, initial_directory=initial
            )
        except Exception as exc:  # noqa: BLE001
            self.snack(self._tr("picker_failed", error=str(exc)))
            return None

    def _toast_export(self, result: export_service.ExportResult) -> None:
        """用 SnackBar 提示导出路径（含改名情况）。

        :param result: 导出结果
        :return: None
        """
        key = "exported_renamed" if result.renamed else "exported"
        self.snack(self._tr(key, path=result.path))

    async def _export_one(self) -> None:
        """导出当前预览为选定格式。

        :return: None
        """
        item = self._active()
        if not item or not item.markdown:
            return
        ext = export_service.format_extension(self.export_format)
        suggested = f"{export_service.build_stem(self.settings, item.path)}.{ext}"
        dest = await self._pick_save_path(suggested)
        if not dest:
            return
        try:
            result = export_service.export_with_format(
                self.settings,
                item.path,
                item.markdown,
                self.export_format,
                output_path=dest,
            )
            self._remember_export_dir(str(Path(dest).expanduser().parent))
            self._toast_export(result)
        except Exception as exc:  # noqa: BLE001
            self.snack(self._tr("export_failed", error=str(exc)))

    async def _export_all(self) -> None:
        """把所有已转换文件导出到选定文件夹。

        :return: None
        """
        done = [i for i in self.items if i.status == "done" and i.markdown]
        if not done:
            return
        directory = await self._pick_export_dir()
        if not directory:
            return
        try:
            last = None
            for item in done:
                last = export_service.export_with_format(
                    self.settings,
                    item.path,
                    item.markdown or "",
                    "md",
                    save_dir=directory,
                )
            self._remember_export_dir(directory)
            if last:
                self._toast_export(last)
        except Exception as exc:  # noqa: BLE001
            self.snack(self._tr("export_failed", error=str(exc)))

    async def _export_zip(self) -> None:
        """把已转换 Markdown 打成 ZIP。

        :return: None
        """
        done = [i for i in self.items if i.status == "done" and i.markdown]
        if len(done) < 2:
            return
        suggested = f"{export_service.build_stem(self.settings, 'markitdown')}.zip"
        dest = await self._pick_save_path(suggested)
        if not dest:
            return
        if not dest.lower().endswith(".zip"):
            dest = f"{dest}.zip"
        try:
            result = export_service.export_zip(
                self.settings,
                [(item.path, item.markdown or "") for item in done],
                dest,
            )
            self._remember_export_dir(str(Path(dest).expanduser().parent))
            self._toast_export(result)
        except Exception as exc:  # noqa: BLE001
            self.snack(self._tr("export_failed", error=str(exc)))

    def _clear(self) -> None:
        """清空队列与预览。

        :return: None
        """
        self.items.clear()
        self.active_id = None
        self.auto_save_dir = None
        self._refresh_workspace()
        self._refresh_preview()
        self.page.update()

    def _open_settings(self, _e: ft.ControlEvent | None = None) -> None:
        """用设置页替换工作区内容。

        :param _e: 点击事件
        :return: None
        """
        def on_changed(settings: AppSettings) -> None:
            """设置即时生效后刷新主界面配色与文案。

            :param settings: 最新设置
            :return: None
            """
            self.settings = settings
            self.colors = apply_theme(self.page, settings.color_scheme)
            self._apply_chrome()
            self._retranslate()
            self._refresh_workspace()
            self._refresh_preview()
            ensure_float_ball(settings.float_ball)
            self.page.update()

        def on_back() -> None:
            """从设置页返回工作区。

            :return: None
            """
            self.shell.content = self.workspace
            self._apply_chrome()
            self._retranslate()
            self._refresh_workspace()
            self._refresh_preview()
            self.page.update()

        settings_page = SettingsPage(
            self.page,
            self.settings,
            on_back=on_back,
            on_changed=on_changed,
            folder_picker=self.folder_picker,
        )
        self.page.padding = 0
        self.page.spacing = 0
        self.shell.content = settings_page.root
        self.page.update()
