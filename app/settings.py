from __future__ import annotations

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
    raw = os.environ.get("XDG_CACHE_HOME", "").strip()
    base = Path(raw) if raw else Path.home() / ".cache"
    return base / "markitdown-gui"


def default_export_dir() -> Path:
    path = cache_root() / "exports"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _is_cache_exports(path: str) -> bool:
    raw = (path or "").strip()
    if not raw:
        return False
    try:
        return Path(raw).expanduser().resolve() == (cache_root() / "exports").resolve()
    except OSError:
        return False


def suggested_save_dir(settings: AppSettings) -> str:
    """Folder to open in the system save dialog."""
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
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> AppSettings:
        known = {f.name for f in fields(cls)}
        filtered = {k: v for k, v in data.items() if k in known}
        if filtered.get("color_scheme") not in SCHEME_IDS:
            filtered["color_scheme"] = "sage"
        if filtered.get("theme") == "dark" and filtered.get("color_scheme") == "snow":
            filtered["color_scheme"] = "ink"
        filtered["theme"] = "dark" if scheme_is_dark(filtered.get("color_scheme")) else "light"
        return cls(**filtered)

    def resolved_save_dir(self) -> str:
        """Headless fallback (MCP). Interactive export always uses a save dialog."""
        raw = (self.default_save_dir or "").strip()
        if raw and not _is_cache_exports(raw):
            path = Path(raw).expanduser()
            path.mkdir(parents=True, exist_ok=True)
            return str(path)
        return str(default_export_dir())


def settings_path() -> Path:
    base = Path.home() / ".config" / "markitdown-gui"
    base.mkdir(parents=True, exist_ok=True)
    return base / "settings.json"


def load_settings() -> AppSettings:
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
        except OSError:
            pass
    settings.theme = "dark" if scheme_is_dark(settings.color_scheme) else "light"
    return settings


def save_settings(settings: AppSettings) -> None:
    path = settings_path()
    path.write_text(
        json.dumps(settings.to_dict(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
