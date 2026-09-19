# MarkItDown GUI (Flet)

Desktop GUI for [Microsoft MarkItDown](https://github.com/microsoft/markitdown), built with **Flet 1.0** + Python 3.14 (`uv`).

## Features

- Choose files (path links; in-memory preview; export via system save dialog)
- Convert modes: immediate / manual button / single-file compact UI
- Batch queue, Markdown preview (source / rendered)
- Export: Markdown, DOCX, HTML, PDF (via bundled Pandoc)
- Settings: language (简体中文 / English), export start folder, color themes (light/dark built in), timestamp prefix, MCP
- Local MCP at `http://127.0.0.1:12768/mcp` — tools `convert_to_text`, `convert_to_file`
- **Primary package:** x86_64 AppImage（内含 `flet-dropzone`，支持系统文件拖放）

## Develop

```bash
uv sync
uv run python main.py
```

开发时用官方轻量桌面客户端，**没有**编译进 `flet-dropzone`，拖放不可用（仍可点击选文件）。要测拖放请用下方 AppImage。

Optional reverse-export binary:

```bash
bash scripts/fetch-pandoc.sh
```

## Build & run AppImage (with drag-and-drop)

```bash
bash scripts/build-appimage.sh          # 用现有 build/linux；无则先 flet build
# 强制重编 Flutter：
# bash scripts/build-appimage.sh --rebuild

./dist/appimage/MarkItDown_GUI-x86_64.AppImage
```

把文件拖到主窗口即可。`flet-dropzone` 就是做这件事的；它只在 **打包进自定义 Flutter 客户端** 的 AppImage / `flet build linux` 产物里生效。

## Install to application menu (Linux)

```bash
bash scripts/install-desktop.sh
```

会把 AppImage 安装到 `~/.local/share/markitdown-gui/`，并创建菜单项与 `markitdown-gui` 命令。

## Flet 1.0 / 拖放说明

| 运行方式 | 客户端 | OS 拖放 |
|----------|--------|---------|
| `uv run python main.py` | 官方轻量 Flet 桌面客户端 | 否 → `Unknown control: flet_dropzone` |
| AppImage / `flet build linux` | 含 `flet-dropzone` + `desktop_drop` 的自编译客户端 | 是 |

Flet 1.0 官方仍无内置「从资源管理器拖文件进窗口」API；社区库 `flet-dropzone`（本仓库 [`vendor/flet-dropzone`](vendor/flet-dropzone)）补上这一能力，但必须随 App 一起打包。

## Packaging placeholders

| Target | Status |
|--------|--------|
| x86_64 AppImage | **主输出**（`scripts/build-appimage.sh`） |
| ARM | CI placeholder |
| rpm | CI placeholder |
| Windows exe | CI placeholder |
| macOS .app | CI placeholder |

## License

MIT (this GUI). MarkItDown is Microsoft MIT. Pandoc is GPL — see its license when redistributing.
