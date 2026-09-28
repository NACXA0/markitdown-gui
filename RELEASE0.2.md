# MarkItDown GUI 0.2

**版本：** 0.2.0（包版本 `0.2.0`）  
**日期：** 2026-09-28  
**平台：** Linux x86_64（amd64）／aarch64（arm64，需在对应宿主机构建）


## 这是什么

MarkItDown GUI 是 [Microsoft MarkItDown](https://github.com/microsoft/markitdown) 的桌面前端。把 PDF、Office、图片等文件转成 Markdown，在窗口里预览，再导出成 Markdown、Word、HTML 或 PDF。

## 本版更新

相对 0.1.1，本版以**悬浮窗修复与体验完善**为主：

### 稳定性

- 修复打包环境（deb / AppImage）开启悬浮窗后短暂闪退（段错误）：X11 `Display*` 经 ctypes 调用时 64 位指针被截断
- 修复自由悬浮时拖入文件被误判为「拖窗结束」而强行贴边
- 修复设置页每次保存都 stop/restart 悬浮窗进程的问题
- 修复界面出现 `Error displaying`（方卡控件在非 Stack 父级上错误设置 `left`/`top`/`expand`）
- Linux 打包时 pip 默认走国内镜像，减轻直连 PyPI 的 SSLEOF / 超时失败

### 悬浮窗交互与布局

- 贴边半藏恢复为窄条，并显示上传 / 文件标志；不再变成空白长条
- 转换完成后复制键从方卡**下方弹出**（窗口就地拉高），不再侧向盖住内容或整窗拉成怪长方形
- 复制键改为圆角矩形，尺寸略增
- 转换中恢复黄黑甜甜圈旋风；复制后礼花改到卡片外层播放，减少被裁切
- 贴边窄条外框变细，减少挡住内部图标

### 文案与其它

- 设置项「悬浮球」更名为「悬浮窗」
- 开发依赖与打包依赖拆分：`flet[all]` 仅用于本地开发，避免打进 site-packages 时版本冲突

## 本版包含

- 选择文件、批量队列；打包后的应用支持从文件管理器拖进窗口
- 三种转换方式：选中后立即转换、手动点「转换」、单文件立即转换（多文件才显示列表）
- 预览：源码 / 渲染（默认渲染）、字数与行数
- 布局：仅文件、文件+预览、仅预览；可拖动调整两侧宽度
- 导出：单个文件、整批到文件夹、整批 ZIP；同名文件自动改名并提示
- 可选时间戳前缀、导出起始文件夹
- 语言：简体中文 / English
- 多套配色（各自带深浅）
- 可选悬浮窗：置顶小窗，拖入单文件转换，完成后可复制 Markdown
- 本机 MCP（默认关闭），地址 `http://127.0.0.1:12768/mcp`，工具 `convert_to_text`、`convert_to_file`。只监听本机，不对外网开放

## 安装包

本版在 x86_64 开发机上实际打出的包（架构名写在文件名里）：

| 文件 | 说明 |
|------|------|
| `dist/deb/markitdown-gui_0.2.0_amd64.deb` | 本版主安装包（Debian / Ubuntu，amd64） |
| `dist/appimage/MarkItDown_GUI-x86_64.AppImage` | 同一构建打出的 x86_64 AppImage |

在 **aarch64** 机器上用同一套命令会得到 `markitdown-gui_0.2.0_arm64.deb` 与 `MarkItDown_GUI-aarch64.AppImage`。

```bash
sudo apt install ./dist/deb/markitdown-gui_0.2.0_amd64.deb
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
# 强制重编：
# bash scripts/build-deb.sh --rebuild
# bash scripts/build-appimage.sh --rebuild
```

若本机直连 PyPI 不稳定，打包脚本会通过 `flet_build_linux_env` 默认使用阿里云 pip 镜像（可用 `PIP_INDEX_URL` / `PIP_TRUSTED_HOST` 覆盖）。

## 本版没有的包

deb / AppImage **不支持交叉编译**：只能在目标架构的宿主机上 `flet build linux` 再打包。

| 目标 | 原因 |
|------|------|
| 在 x86 上打 ARM Linux 包（或反过来） | 无交叉编译；须在对应架构机器上构建 |
| Windows `.exe`（x64） | 有 `scripts/build-windows.cmd`，只能在 Windows 上跑 |
| ARM Windows `.exe` | 预构建运行时只有 Windows x64 |
| `.rpm` | 没有打包脚本 |
| macOS `.app` | 占位，未实现 |

## 已知限制

- `uv run python main.py` 用的是官方轻量客户端，**没有**系统拖放。拖放只在 deb / AppImage / `flet build linux` 里可用
- 悬浮窗的系统拖放同样依赖打包客户端中的 `flet-dropzone`
- PDF 等反向导出依赖随包的 Pandoc。Pandoc 是 GPL，再分发时需遵守其许可证
- 公开测试阶段不保证设置项、MCP 工具名或安装路径在下一版保持不变

## 许可

本 GUI 采用 Apache License 2.0（见仓库 `LICENSE`），没有附加商业条款。MarkItDown 本体为 Microsoft MIT。随包 Pandoc 为 GPL。

## 反馈

问题与建议请提到 <https://github.com/NACXA0/markitdown-gui/issues>。说明系统版本、安装方式（deb / AppImage），以及复现步骤。
