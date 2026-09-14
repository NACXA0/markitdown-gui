from __future__ import annotations

from dataclasses import dataclass
from threading import Lock

_lock = Lock()
_md = None


@dataclass
class ConvertOutcome:
    path: str
    ok: bool
    markdown: str | None = None
    error: str | None = None


def _get_engine():
    global _md
    with _lock:
        if _md is None:
            from markitdown import MarkItDown

            _md = MarkItDown(enable_plugins=False)
        return _md


def convert_file(path: str) -> ConvertOutcome:
    try:
        result = _get_engine().convert_local(path)
        markdown = getattr(result, "markdown", None) or str(result)
        return ConvertOutcome(path=path, ok=True, markdown=markdown)
    except Exception as exc:  # noqa: BLE001 — surface to UI
        return ConvertOutcome(
            path=path,
            ok=False,
            error=f"{type(exc).__name__}: {exc}",
        )
