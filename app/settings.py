from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, fields
from pathlib import Path
from typing import Any, Literal

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


@dataclass
class AppSettings:
    language: str = "zh"
    default_save_dir: str = ""
    convert_mode: ConvertMode = "drop_immediate"
    theme: ThemeMode = "light"
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
        return cls(**filtered)

    def resolved_save_dir(self) -> str:
        if self.default_save_dir.strip():
            return self.default_save_dir
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
    if not settings.default_save_dir.strip():
        settings.default_save_dir = str(default_export_dir())
    else:
        Path(settings.default_save_dir).mkdir(parents=True, exist_ok=True)
    return settings


def save_settings(settings: AppSettings) -> None:
    if not settings.default_save_dir.strip():
        settings.default_save_dir = str(default_export_dir())
    path = settings_path()
    path.write_text(
        json.dumps(settings.to_dict(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
