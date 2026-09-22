
"""应用设置的加载、保存与路径约定。

配置文件位于 ``~/.config/markitdown-gui/settings.json``；
默认导出目录在 XDG 缓存下的 ``exports``。
"""

import json
import os
from dataclasses import asdict, dataclass, fields
from pathlib import Path
from typing import Any, Literal

from app.theme import SCHEME_IDS, scheme_is_dark

ConvertMode = Literal[
    "drop_immediate",
    "manual_button",
    "single_immediate_multi_list",
]
ThemeMode = Literal["light", "dark"]


def cache_root() -> Path:
    """应用缓存根目录。

    :return: ``$XDG_CACHE_HOME/markitdown-gui`` 或 ``~/.cache/markitdown-gui``
    """
    raw = os.environ.get("XDG_CACHE_HOME", "").strip()
    base = Path(raw) if raw else Path.home() / ".cache"
    return base / "markitdown-gui"


def default_export_dir() -> Path:
    """默认导出目录（必要时创建）。

    :return: 缓存目录下的 ``exports``
    """
    path = cache_root() / "exports"
    try:
        path.mkdir(parents=True, exist_ok=True)
    except (OSError, UnicodeError):
        path = Path.home() / ".cache" / "markitdown-gui" / "exports"
        try:
            path.mkdir(parents=True, exist_ok=True)
        except (OSError, UnicodeError):
            pass
    return path


def _is_cache_exports(path: str) -> bool:
    """判断路径是否就是默认缓存导出目录。
    :param path: 待比较的路径字符串
    :return: 解析后与默认导出目录相同则为 True
    """
    raw = (path or "").strip()
    if not raw:
        return False
    try:
        return Path(raw).expanduser().resolve() == (cache_root() / "exports").resolve()
    except OSError:
        return False


def suggested_save_dir(settings: AppSettings) -> str:
    """系统保存对话框打开时使用的文件夹。
    :param settings: 当前应用设置
    :return: 已存在的目录路径字符串
    """
    raw = (settings.default_save_dir or "").strip()
    if raw:
        path = Path(raw).expanduser()
        if path.is_dir():
            return str(path)
        if path.parent.is_dir():
            return str(path.parent)
    return str(default_export_dir())


@dataclass
class AppSettings:
    """持久化的用户偏好。
    :param language: 界面语言（zh / en）
    :param default_save_dir: 导出对话框起始目录
    :param convert_mode: 选择文件后如何触发转换
    :param theme: 由配色推导的浅/深色标记
    :param color_scheme: 配色方案 id
    :param float_ball: 是否启用独立置顶悬浮球窗口
    :param timestamp_prefix: 导出文件名是否加时间戳
    :param mcp_enabled: 是否启动本机 MCP HTTP 服务
    :param mcp_port: MCP 监听端口
    :param float_ball_x: 预留的悬浮球窗口 X 坐标
    :param float_ball_y: 预留的悬浮球窗口 Y 坐标
    """

    language: str = "zh"
    default_save_dir: str = ""
    convert_mode: ConvertMode = "drop_immediate"
    theme: ThemeMode = "light"
    color_scheme: str = "sage"
    float_ball: bool = False
    timestamp_prefix: bool = False
    mcp_enabled: bool = False
    mcp_port: int = 12768
    float_ball_x: float | None = None
    float_ball_y: float | None = None

    def to_dict(self) -> dict[str, Any]:
        """转为可 JSON 序列化的字典。

        :return: 字段名到取值的映射
        """
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> AppSettings:
        """从字典恢复设置，忽略未知键并校正非法配色。

        :param data: 通常来自 settings.json
        :return: 规范化后的设置对象
        """
        known = {f.name for f in fields(cls)}
        filtered = {k: v for k, v in data.items() if k in known}
        if filtered.get("color_scheme") not in SCHEME_IDS:
            filtered["color_scheme"] = "sage"
        if filtered.get("theme") == "dark" and filtered.get("color_scheme") == "snow":
            filtered["color_scheme"] = "ink"
        filtered["theme"] = "dark" if scheme_is_dark(filtered.get("color_scheme")) else "light"
        return cls(**filtered)

    def resolved_save_dir(self) -> str:
        """无界面时的回退目录（MCP）。交互式导出始终使用保存对话框。

        :return: 可写入的导出目录路径
        """
        raw = (self.default_save_dir or "").strip()
        if raw and not _is_cache_exports(raw):
            path = Path(raw).expanduser()
            path.mkdir(parents=True, exist_ok=True)
            return str(path)
        return str(default_export_dir())


def settings_path() -> Path:
    """设置文件路径（必要时创建配置目录）。

    :return: ``~/.config/markitdown-gui/settings.json``
    """
    base = Path.home() / ".config" / "markitdown-gui"
    try:
        base.mkdir(parents=True, exist_ok=True)
    except (OSError, UnicodeError):
        pass
    return base / "settings.json"


def load_settings() -> AppSettings:
    """读取磁盘设置；损坏或缺失时回退默认值。

    :return: 当前有效设置
    """
    path = settings_path()
    settings = AppSettings()
    if path.exists():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                settings = AppSettings.from_dict(data)
        except (OSError, json.JSONDecodeError, TypeError, ValueError):
            settings = AppSettings()
    raw = settings.default_save_dir.strip()
    if not raw:
        settings.default_save_dir = str(default_export_dir())
    else:
        try:
            Path(raw).expanduser().mkdir(parents=True, exist_ok=True)
        except (OSError, UnicodeError):
            # AppImage 子进程若 locale 为 ASCII，含中文路径的 mkdir 会抛 UnicodeEncodeError
            pass
    settings.theme = "dark" if scheme_is_dark(settings.color_scheme) else "light"
    return settings


def save_settings(settings: AppSettings) -> None:
    """把设置写入 JSON 文件。
    :param settings: 要持久化的设置
    :return: None
    """
    path = settings_path()
    path.write_text(
        json.dumps(settings.to_dict(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
