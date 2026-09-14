# MarkItDown GUI (Flet)

Desktop GUI for [Microsoft MarkItDown](https://github.com/microsoft/markitdown), built with **Flet** + Python 3.14 (`uv`).

## Features

- Choose files and convert to Markdown (in-memory preview; export to save)
- Convert modes: immediate / manual button / single-file compact UI
- Batch queue, Markdown preview (source / rendered)
- Export: Markdown, DOCX, HTML, PDF (via bundled Pandoc)
- Settings: language (zh/en), save folder, dark mode, float ball, timestamp prefix, MCP
- Local MCP at `http://127.0.0.1:12768/mcp` — tools `convert_to_text`, `convert_to_file`
- Default package target: **x86_64 AppImage**

## Develop

```bash
uv sync
uv run python main.py
```

> 系统文件拖放依赖 `flet-dropzone`，需要使用下方 **Linux 构建包** 运行。  
> `uv run python main.py` 走官方轻量客户端，**不支持** OS 拖放（仍可点击选文件）。

Optional reverse-export binary:

```bash
bash scripts/fetch-pandoc.sh
```

## Run Linux build (with drag-and-drop)

```bash
bash scripts/run-linux.sh
# 或直接：
# ./build/linux/bundle/markitdown-gui
```

把文件拖到主窗口**左侧区域**即可。

## Build AppImage

```bash
bash scripts/build-appimage.sh
```

Produces PyInstaller output under `dist/`, and an AppImage under `dist/appimage/` when `appimagetool` is installed.

## Packaging placeholders

| Target | Status |
|--------|--------|
| x86_64 AppImage | Primary (`scripts/build-appimage.sh`) |
| ARM | CI placeholder |
| rpm | CI placeholder |
| Windows exe | CI placeholder |
| macOS .app | CI placeholder |

## License

MIT (this GUI). MarkItDown is Microsoft MIT. Pandoc is GPL — see its license when redistributing.
