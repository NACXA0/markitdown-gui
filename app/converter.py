"""文件转 Markdown 引擎封装。

对 Microsoft MarkItDown 做单例包装，把转换结果统一成 ``ConvertOutcome``，
供界面与 MCP 服务调用。
"""

from dataclasses import dataclass
from threading import Lock
from typing import Any

_lock = Lock()
_md: Any = None


@dataclass
class ConvertOutcome:
    """单次文件转换的结果。
    :param path: 源文件路径
    :param ok: 是否转换成功
    :param markdown: 成功时的 Markdown 文本
    :param error: 失败时的错误说明
    """

    path: str
    ok: bool
    markdown: str | None = None
    error: str | None = None


def _get_engine() -> Any:
    """懒加载并复用 MarkItDown 实例（线程安全）。

    :return: MarkItDown 转换引擎
    """
    global _md
    with _lock:
        if _md is None:
            from markitdown import MarkItDown

            _md = MarkItDown(enable_plugins=False)
        return _md


def convert_file(path: str) -> ConvertOutcome:
    """将本地文件转换为 Markdown。
    :param path: 源文件绝对或相对路径
    :return: 转换结果；失败时 ``ok`` 为 False 并带 ``error``
    """
    try:
        result = _get_engine().convert_local(path)
        markdown = getattr(result, "markdown", None) or str(result)
        return ConvertOutcome(path=path, ok=True, markdown=markdown)
    except Exception as exc:  # noqa: BLE001 —— 将异常暴露给界面
        return ConvertOutcome(
            path=path,
            ok=False,
            error=f"{type(exc).__name__}: {exc}",
        )
