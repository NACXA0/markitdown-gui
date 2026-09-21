# MarkItDown GUI 0.1.1

**版本：** 0.1.1（包版本 `0.1.1`）  
**日期：** 2026-09-21  
**平台：** Linux x86_64（amd64）


## 这是什么

MarkItDown GUI 是 [Microsoft MarkItDown](https://github.com/microsoft/markitdown) 的桌面前端。把 PDF、Office、图片等文件转成 Markdown，在窗口里预览，再导出成 Markdown、Word、HTML 或 PDF。

## 本版更新

相对 0.1.0：

- 设置页底部增加了说明（关于本程序、许可证与仓库入口）
- README 增加了从源码构建教程
- Linux 打包脚本按宿主架构自动选择（amd64 / arm64、x86_64 / aarch64），产物文件名带架构后缀；仍不支持交叉编译

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

本版在 x86_64 开发机上实际打出的包（架构名写在文件名里）：

| 文件 | 说明 |
|------|------|
| `dist/deb/markitdown-gui_0.1.1_amd64.deb` | 本版主安装包（Debian / Ubuntu，amd64，约 235 MB） |
| `dist/appimage/MarkItDown_GUI-x86_64.AppImage` | 同一构建打出的 x86_64 AppImage（约 217 MB） |

在 **aarch64** 机器上用同一套命令会得到 `markitdown-gui_0.1.1_arm64.deb` 与 `MarkItDown_GUI-aarch64.AppImage`。

```bash
sudo apt install ./dist/deb/markitdown-gui_0.1.1_amd64.deb
```

装好后可从应用菜单启动，或在终端运行 `markitdown-gui`。程序装在 `/opt/markitdown-gui`。

AppImage 直接运行：

```bash
./dist/appimage/MarkItDown_GUI-x86_64.AppImage
```

重新打包（脚本自动按 `uname -m` 选架构；已有匹配的 `build/linux` 时直接装包，要重编客户端时加 `--rebuild`）：

```bash
bash scripts/build-deb.sh
bash scripts/build-appimage.sh
```

## 本版没有的包

deb / AppImage **不支持交叉编译**：只能在目标架构的宿主机上 `flet build linux` 再打包。`scripts/build-deb.sh` 与 `scripts/build-appimage.sh` 会检测宿主架构、校验二进制 `file` 输出，并把架构写进产物名；在 x86_64 上不会生成 arm64 包。

当前仓库另外也不能打出：

| 目标 | 原因 |
|------|------|
| 在 x86 上打 ARM Linux 包（或反过来） | 无交叉编译；须在对应架构机器上构建 |
| Windows `.exe`（含 ARM Windows） | 没有打包脚本。`flet build windows` 只能在 Windows 上跑 |
| `.rpm` | 没有打包脚本，也没有 `rpmbuild` / `fpm` |
| macOS `.app` | 占位，未实现。`flet build macos` 只能在 macOS 上跑 |

## 已知限制

- `uv run python main.py` 用的是官方轻量客户端，**没有**系统拖放。拖放只在 deb / AppImage / `flet build linux` 里可用
- PDF 等反向导出依赖随包的 Pandoc。Pandoc 是 GPL，再分发时需遵守其许可证
- 公开测试阶段不保证设置项、MCP 工具名或安装路径在下一版保持不变

## 许可

本 GUI 采用 Apache License 2.0（见仓库 `LICENSE`），没有附加商业条款。MarkItDown 本体为 Microsoft MIT。随包 Pandoc 为 GPL。

## 反馈

问题与建议请提到 <https://github.com/NACXA0/markitdown-gui/issues>。说明系统版本、安装方式（deb），以及复现步骤。
