
"""本机 MCP HTTP 服务。

在 127.0.0.1 上提供 JSON-RPC：把本地文件转成 Markdown 文本或写出文件，
供 Cursor 等 MCP 客户端调用。
"""

import threading
from typing import Any

import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app import converter, export_service
from app.settings import AppSettings, load_settings

_server: uvicorn.Server | None = None
_thread: threading.Thread | None = None
_lock = threading.Lock()
_running = False
_port = 12768


def is_running() -> bool:
    """服务线程是否仍在运行。

    :return: 正在监听则为 True
    """
    return _running


def current_url() -> str:
    """当前 MCP 端点 URL。

    :return: ``http://127.0.0.1:<port>/mcp``
    """
    return f"http://127.0.0.1:{_port}/mcp"


def _build_app() -> FastAPI:
    """构建 FastAPI 应用（健康检查与 JSON-RPC）。

    :return: 配置好的 FastAPI 实例
    """
    api = FastAPI(title="markitdown-gui-mcp")

    @api.get("/health")
    def health() -> dict[str, str]:
        """存活探测。

        :return: 固定 ``{"status": "ok"}``
        """
        return {"status": "ok"}

    @api.get("/mcp")
    def info() -> dict[str, Any]:
        """GET /mcp：服务说明。

        :return: 名称、版本、工具列表等元数据
        """
        return {
            "name": "markitdown-gui-mcp",
            "version": "0.1.1",
            "tools": ["convert_to_text", "convert_to_file"],
            "transport": "json-rpc-http",
            "note": "POST JSON-RPC to /mcp. Methods: tools/list, tools/call",
        }

    @api.post("/mcp")
    async def rpc(request: Request) -> JSONResponse:
        """处理 JSON-RPC POST。

        :param request: FastAPI 请求
        :return: JSON-RPC result 或 error
        """
        body = await request.json()
        req_id = body.get("id")
        method = body.get("method") or ""
        params = body.get("params") or {}

        try:
            result = await _dispatch(method, params)
            return JSONResponse(
                {"jsonrpc": "2.0", "id": req_id, "result": result}
            )
        except Exception as exc:  # noqa: BLE001
            return JSONResponse(
                {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "error": {"code": -32000, "message": str(exc)},
                }
            )

    return api


async def _dispatch(method: str, params: dict[str, Any]) -> Any:
    """按 MCP 方法名分发。
    :param method: JSON-RPC method
    :param params: 方法参数
    :return: 方法结果对象
    :raises ValueError: 未知方法
    """
    if method in {"initialize", "notifications/initialized"}:
        return {
            "protocolVersion": "2024-11-05",
            "capabilities": {"tools": {}},
            "serverInfo": {"name": "markitdown-gui", "version": "0.1.1"},
        }
    if method == "ping":
        return {}
    if method == "tools/list":
        return {
            "tools": [
                {
                    "name": "convert_to_text",
                    "description": "Convert a local file to Markdown and return the text.",
                    "inputSchema": {
                        "type": "object",
                        "properties": {
                            "path": {
                                "type": "string",
                                "description": "Absolute path to the source file",
                            }
                        },
                        "required": ["path"],
                    },
                },
                {
                    "name": "convert_to_file",
                    "description": "Convert a local file to Markdown and save it.",
                    "inputSchema": {
                        "type": "object",
                        "properties": {
                            "path": {"type": "string"},
                            "save_dir": {
                                "type": "string",
                                "description": "Optional output directory",
                            },
                        },
                        "required": ["path"],
                    },
                },
            ]
        }
    if method == "tools/call":
        return _call_tool(params)
    raise ValueError(f"Method not found: {method}")


def _call_tool(params: dict[str, Any]) -> dict[str, Any]:
    """执行 convert_to_text / convert_to_file。
    :param params: 含 ``name`` 与 ``arguments`` 的 tools/call 参数
    :return: MCP content 响应
    :raises ValueError: 缺路径或未知工具
    :raises RuntimeError: 转换失败
    """
    name = params.get("name")
    args = params.get("arguments") or {}
    path = args.get("path")
    if not path:
        raise ValueError("Missing path")

    outcome = converter.convert_file(str(path))
    if not outcome.ok or not outcome.markdown:
        raise RuntimeError(outcome.error or "Conversion failed")

    if name == "convert_to_text":
        return {"content": [{"type": "text", "text": outcome.markdown}]}

    if name == "convert_to_file":
        settings = load_settings()
        save_dir = args.get("save_dir")
        result = export_service.export_markdown(
            settings, str(path), outcome.markdown, save_dir
        )
        text = (
            f"path={result.path}\nrenamed={result.renamed}\n"
            f"original_name={result.original_name}"
        )
        return {"content": [{"type": "text", "text": text}]}

    raise ValueError(f"Unknown tool: {name}")


def start(port: int = 12768) -> None:
    """在后台线程启动 uvicorn（仅监听本机）。
    :param port: 监听端口
    :return: None
    """
    global _server, _thread, _running, _port
    stop()
    with _lock:
        _port = port
        config = uvicorn.Config(
            _build_app(),
            host="127.0.0.1",
            port=port,
            log_level="warning",
            access_log=False,
        )
        server = uvicorn.Server(config)
        _server = server
        _running = True

        def _run() -> None:
            """阻塞运行 uvicorn，退出时清除运行标志。

            :return: None
            """
            global _running
            try:
                server.run()
            finally:
                _running = False

        _thread = threading.Thread(target=_run, name="mcp-server", daemon=True)
        _thread.start()


def stop() -> None:
    """停止 MCP HTTP 服务并释放端口。

    :return: None
    """
    global _server, _thread, _running
    with _lock:
        server = _server
        thread = _thread
        if server is not None:
            server.should_exit = True
            server.force_exit = True
        _running = False

    if thread is not None and thread.is_alive():
        thread.join(timeout=3.0)

    with _lock:
        if _server is server:
            _server = None
        if _thread is thread:
            _thread = None


def apply_setting(settings: AppSettings) -> None:
    """按设置开关 MCP 服务。
    :param settings: 含 ``mcp_enabled`` 与 ``mcp_port``
    :return: None
    """
    if settings.mcp_enabled:
        start(settings.mcp_port)
    else:
        stop()
