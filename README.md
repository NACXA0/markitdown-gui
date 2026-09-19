# MarkItDown GUI（基于 Flet）
[Microsoft MarkItDown](https://github.com/microsoft/markitdown) 的桌面图形界面，采用 **Flet 1.0** + Python 3.14（`uv`）构建。

## 功能特性
- 文件选择（支持路径链接；内存内预览；通过系统保存对话框导出）
- 转换模式：即时转换 / 手动按钮触发 / 单文件精简界面
- 批量任务队列，Markdown 预览（源码视图 / 渲染视图）
- 导出格式：Markdown、DOCX、HTML、PDF（内置 Pandoc）
- 设置项：界面语言（简体中文 / English）、导出起始目录、配色主题（内置浅色/深色）、时间戳前缀、MCP
- 本地 MCP 服务地址：`[http://127.0.0.1:12768/mcp](http://127.0.0.1:12768/mcp)`，提供工具：`convert_to_text`、`convert_to_file`
- **公开测试主包**：amd64 `.deb`（内置 `flet-dropzone`，支持系统文件拖放）。说明见 [RELEASE.md](RELEASE.md)

## 开发
```bash
uv sync
uv run python main.py
```
开发环境使用官方轻量桌面客户端，**未编译打包 `flet-dropzone`，拖放功能不可用**（仍可点击选择文件）。如需测试拖放，请使用下文的 AppImage。

可选：拉取反向导出所需二进制程序
```bash
bash scripts/fetch-pandoc.sh
```

## 构建并运行支持拖放的 AppImage
```bash
bash scripts/build-appimage.sh          # 使用已有的 build/linux；若无则先执行 flet build
# 强制重新编译 Flutter：
# bash scripts/build-appimage.sh --rebuild
./dist/appimage/MarkItDown_GUI-x86_64.AppImage
```
直接将文件拖入主窗口即可。`flet-dropzone` 负责实现该能力；该组件仅在**打包到自定义 Flutter 客户端**的 AppImage / `flet build linux` 产物中生效。

## Linux：安装到应用程序菜单
```bash
bash scripts/install-desktop.sh
```
脚本会将 AppImage 安装至 `~/.local/share/markitdown-gui/`，同时创建桌面菜单项和 `markitdown-gui` 系统命令。

## Flet 1.0 / 文件拖放说明
| 运行方式 | 客户端类型 | 系统文件拖放 |
|----------|--------|---------|
| `uv run python main.py` | Flet 官方轻量桌面客户端 | 否 → 报错 `Unknown control: flet_dropzone` |
| deb / AppImage / `flet build linux` | 内置 `flet-dropzone` + `desktop_drop` 的自编译客户端 | 是 |

Flet 1.0 官方尚未内置「从资源管理器拖拽文件到应用窗口」的API；社区库 `flet-dropzone`（仓库路径 [`vendor/flet-dropzone`](vendor/flet-dropzone)）补充了这项能力，但该库必须随应用一同打包。

## 打包
```bash
bash scripts/build-deb.sh               # 用现有 build/linux 打 amd64 deb
# bash scripts/build-deb.sh --rebuild   # 先 flet build linux
```
产物：`dist/deb/markitdown-gui_0.1.0_amd64.deb`。

| 目标平台包 | 状态 |
|--------|--------|
| amd64 deb | **公开测试主包**（`scripts/build-deb.sh`） |
| x86_64 AppImage | 开发机可打（`scripts/build-appimage.sh`） |
| ARM | 占位，未实现 |
| rpm | 占位，未实现（无打包脚本，也无 rpmbuild） |
| Windows exe | 占位，未实现（只能在 Windows 上 `flet build windows`） |
| macOS .app | 占位，未实现 |

## 许可证
本图形界面采用 Apache License 2.0（见仓库根目录 `LICENSE`）。MarkItDown 为微软 MIT 协议。Pandoc 使用 GPL 协议——重新分发时请查阅其许可证。