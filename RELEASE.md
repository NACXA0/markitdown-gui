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

本版在 x86_64 开发机上实际打出的包：

| 文件 | 说明 |
|------|------|
| `dist/deb/markitdown-gui_0.1.1_amd64.deb` | 本版主安装包（Debian / Ubuntu，amd64，约 235 MB） |
| `dist/appimage/MarkItDown_GUI-x86_64.AppImage` | 同一构建打出的 x86_64 AppImage（约 217 MB） |

```bash
sudo apt install ./dist/deb/markitdown-gui_0.1.1_amd64.deb
```

装好后可从应用菜单启动，或在终端运行 `markitdown-gui`。程序装在 `/opt/markitdown-gui`。

AppImage 直接运行：

```bash
./dist/appimage/MarkItDown_GUI-x86_64.AppImage
```

重新打包（已有 `build/linux` 时直接装包；要重编客户端时加 `--rebuild`）：

```bash
bash scripts/build-deb.sh
bash scripts/build-appimage.sh
```

## 本版没有的包

ARM 的 deb 和 AppImage **不能在这台 x86_64 机器上制作**。`flet build linux` 只编译当前机器的架构；`--arch` 只对 macOS 和 Android 有效，不作用于 Linux。本机没有 aarch64 交叉编译器，也没有 qemu-user。打包脚本只是把已经编好的客户端装进 deb / AppImage，没有 ARM 二进制就打不出能在 ARM 上运行的包。把 deb 的 `Architecture` 改成 `arm64` 只会得到里面仍是 x86_64 程序的坏包。要出 ARM 包，需要在 ARM 机器（或 ARM 虚拟机）上执行同样的 `flet build linux`，再打包。

当前仓库另外也不能打出：

| 目标 | 原因 |
|------|------|
| ARM64 Linux deb / AppImage | 见上。x86_64 上不能交叉编译 |
| Windows `.exe`（含 ARM Windows） | 没有打包脚本。`flet build windows` 只能在 Windows 上跑，这里是 Linux |
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
