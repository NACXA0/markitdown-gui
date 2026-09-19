# MarkItDown GUI 0.1

**版本：** 0.1（包版本 `0.1.0`）   
**日期：** 2026-09-19  
**平台：** Linux x86_64（amd64）


## 这是什么

MarkItDown GUI 是 [Microsoft MarkItDown](https://github.com/microsoft/markitdown) 的桌面前端。把 PDF、Office、图片等文件转成 Markdown，在窗口里预览，再导出成 Markdown、Word、HTML 或 PDF。

## 本版包含

- 选择文件、批量队列；打包后的应用支持从文件管理器拖进窗口
- 三种转换方式：选中后立即转换、手动点「转换」、单文件立即转换（多文件才显示列表）
- 预览：源码 / 渲染（默认渲染）、字数与行数
- 布局：仅文件、文件+预览、仅预览；可拖动调整两侧宽度
- 文件列表显示完整文件名、类型图标和体积
- 导出：单个文件、整批到文件夹、整批 ZIP；同名文件自动改名并提示
- 可选时间戳前缀、导出起始文件夹
- 语言：简体中文 / English
- 多套配色（各自带深浅）
- 可选悬浮球：置顶小窗，拖入文件即转换
- 本机 MCP（默认关闭），地址 `http://127.0.0.1:12768/mcp`，工具 `convert_to_text`、`convert_to_file`。只监听本机，不对外网开放

## 安装包

| 文件 | 说明 |
|------|------|
| `dist/deb/markitdown-gui_0.1.0_amd64.deb` | 本版主安装包（Debian / Ubuntu，amd64） |

```bash
sudo apt install ./dist/deb/markitdown-gui_0.1.0_amd64.deb
```

装好后可从应用菜单启动，或在终端运行 `markitdown-gui`。程序装在 `/opt/markitdown-gui`。

重新打包：

```bash
bash scripts/build-deb.sh
```

已有 Linux 构建时直接打包；需要重编客户端时加 `--rebuild`。

## 本版没有的包

当前仓库**不能**打出下面这些包，本机环境也不具备交叉编译条件，所以 0.1 不提供：

| 目标 | 原因 |
|------|------|
| Windows `.exe` | 没有打包脚本。`flet build windows` 只能在 Windows 上跑，这里是 Linux |
| `.rpm` | 没有打包脚本，也没有 `rpmbuild` / `fpm` |
| ARM Linux | 占位，未实现 |
| macOS `.app` | 占位，未实现 |

x86_64 AppImage 仍可由 `scripts/build-appimage.sh` 在开发机上生成，但不是这次公开测试随包发布的安装介质。

## 已知限制

- `uv run python main.py` 用的是官方轻量客户端，**没有**系统拖放。拖放只在 deb / AppImage / `flet build linux` 里可用
- PDF 等反向导出依赖随包的 Pandoc。Pandoc 是 GPL，再分发时需遵守其许可证
- 公开测试阶段不保证设置项、MCP 工具名或安装路径在下一版保持不变

## 许可

本 GUI 采用 Apache License 2.0（见仓库 `LICENSE`），没有附加商业条款。MarkItDown 本体为 Microsoft MIT。随包 Pandoc 为 GPL。

## 反馈

问题与建议请提到 <https://github.com/NACXA0/markitdown-gui/issues>。说明系统版本、安装方式（deb），以及复现步骤。
