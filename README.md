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

## 从源码构建

在 **Linux x86_64（amd64）或 aarch64（arm64）** 本机上可从源码打出对应架构的客户端和安装包。脚本按 `uname -m` 自动选择架构，产物文件名里带架构后缀；**不支持交叉编译**（不能在 x86 机器上打出 ARM 包，反之亦然）。只想改界面、看转换结果时，做到第 3 步即可；要测系统拖放或得到安装包，继续做到第 5 步及以后。

### 1. 准备环境

需要：

- Linux x86_64 或 aarch64（Debian、Ubuntu 及其衍生版）
- Git、curl
- [uv](https://docs.astral.sh/uv/)：按仓库里的 `.python-version` 安装 **Python 3.14**

尚未安装 uv 时：

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

编译带拖放的 Linux 客户端（第 5 步）前，还要装 GTK / Flutter 链接依赖。这组包与 [Flet Linux 打包文档](https://flet.dev/docs/publish/linux/) 一致：

```bash
sudo apt update
sudo apt install -y \
  binutils clang cmake llvm lld ninja-build pkg-config \
  libgtk-3-dev libsecret-1-0 libsecret-1-dev libunwind-dev \
  gstreamer1.0-alsa gstreamer1.0-gl gstreamer1.0-gtk3 gstreamer1.0-libav \
  gstreamer1.0-plugins-bad gstreamer1.0-plugins-base gstreamer1.0-plugins-good \
  gstreamer1.0-plugins-ugly gstreamer1.0-pulseaudio gstreamer1.0-qt5 \
  gstreamer1.0-tools gstreamer1.0-x \
  libasound2-dev libgstreamer1.0-dev \
  libgstreamer-plugins-base1.0-dev libgstreamer-plugins-bad1.0-dev \
  libmpv-dev mpv
```

`lld` 必须存在，否则链接阶段会失败。首次 `flet build` 若本机没有匹配版本的 Flutter，会自动下载到 `$HOME/flutter/`，需要网络，耗时较长。打 deb 使用系统自带的 `dpkg-deb`。

### 2. 获取代码并安装 Python 依赖

```bash
git clone https://github.com/NACXA0/markitdown-gui.git
cd markitdown-gui
uv sync
```

`uv sync` 会创建 `.venv`，并装上 Flet、MarkItDown 以及仓库内的 `vendor/flet-dropzone`。

### 3. 开发模式运行

```bash
uv run python main.py
```

这一步用的是 Flet 官方轻量桌面客户端，**没有编译 `flet-dropzone`，从文件管理器拖放文件不可用**（仍可点击选择文件）。拖文件进窗口请用第 5 步之后的产物。

### 4. 准备 Pandoc（导出 DOCX / HTML / PDF）

反向导出依赖 Pandoc 二进制。打包脚本在缺失时会自动下载；开发模式不会，缺了会提示你先执行：

```bash
bash scripts/fetch-pandoc.sh
```

成功后二进制在 `bin/pandoc`（默认 3.6.4，可用环境变量 `PANDOC_VERSION` 指定版本）。Pandoc 为 GPL，再分发时需遵守其许可证。

### 5. 编译带拖放的 Linux 客户端

```bash
env -u ANDROID_HOME uv run flet build linux --skip-flutter-doctor
bash scripts/run-linux.sh
```

产物在 `build/linux/markitdown-gui`。`scripts/run-linux.sh` 会启动这份发布包（找不到时会提示先完成上面的编译）。清掉 `ANDROID_HOME` 是为了避免本机 Android SDK 干扰 Flutter 的 Linux 构建。

改过 Python 代码或 `vendor/flet-dropzone` 后，不要复用旧的 `build/linux`，按下面第 6 或第 7 步加上 `--rebuild`，或重新执行本步命令。

### 6. 打 AppImage

```bash
bash scripts/build-appimage.sh
# 已有 build/linux 但需要重编客户端时：
# bash scripts/build-appimage.sh --rebuild
```

产物（二选一，取决于宿主）：

- `dist/appimage/MarkItDown_GUI-x86_64.AppImage`
- `dist/appimage/MarkItDown_GUI-aarch64.AppImage`

没有现成的、且架构匹配的 `build/linux` 时，脚本会先执行 `flet build linux`。`appimagetool` 按架构下载到 `bin/appimagetool-x86_64` 或 `bin/appimagetool-aarch64`。

装进当前用户的应用程序菜单（不需要 root）：

```bash
bash scripts/install-desktop.sh
```

脚本安装与当前宿主架构对应的 AppImage 到 `~/.local/share/markitdown-gui/`，并创建桌面菜单项和 `~/.local/bin/markitdown-gui`。请确认 `~/.local/bin` 在 `PATH` 中。

### 7. 打 deb 并安装

架构由宿主决定（`amd64` 或 `arm64`）。版本号取自 `pyproject.toml` 的 `project.version`（当前为 `0.1.1`）：

```bash
bash scripts/build-deb.sh
# bash scripts/build-deb.sh --rebuild
# 例：sudo apt install ./dist/deb/markitdown-gui_0.1.1_amd64.deb
# 或：sudo apt install ./dist/deb/markitdown-gui_0.1.1_arm64.deb
sudo apt install ./dist/deb/markitdown-gui_0.1.1_*.deb
```

装好后从应用菜单启动，或在终端运行 `markitdown-gui`。程序在 `/opt/markitdown-gui`。

## Flet 1.0 / 文件拖放说明
| 运行方式 | 客户端类型 | 系统文件拖放 |
|----------|--------|---------|
| `uv run python main.py` | Flet 官方轻量桌面客户端 | 否 → 报错 `Unknown control: flet_dropzone` |
| deb / AppImage / `flet build linux` | 内置 `flet-dropzone` + `desktop_drop` 的自编译客户端 | 是 |

Flet 1.0 官方尚未内置「从资源管理器拖拽文件到应用窗口」的 API；社区库 `flet-dropzone`（仓库路径 [`vendor/flet-dropzone`](vendor/flet-dropzone)）补充了这项能力，但该库必须随应用一同打包。

## 各平台打包状态

命令见上文「从源码构建」。各目标目前的情况：

| 目标平台包 | 状态 |
|--------|--------|
| amd64 deb | 在 x86_64 主机上：`scripts/build-deb.sh` → `markitdown-gui_<ver>_amd64.deb` |
| arm64 deb | 在 aarch64 主机上：同一脚本 → `markitdown-gui_<ver>_arm64.deb`（不可交叉编译） |
| x86_64 AppImage | 在 x86_64 主机上：`scripts/build-appimage.sh` → `MarkItDown_GUI-x86_64.AppImage` |
| aarch64 AppImage | 在 aarch64 主机上：同一脚本 → `MarkItDown_GUI-aarch64.AppImage`（不可交叉编译） |
| rpm | 占位，未实现（无打包脚本，也无 rpmbuild） |
| Windows exe | 占位，未实现（只能在 Windows 上 `flet build windows`；无本仓库打包脚本） |
| ARM Windows exe | 占位，未实现（只能在 Windows 上 `flet build windows`） |
| macOS .app | 占位，未实现 |

## 许可证
本图形界面采用 Apache License 2.0（见仓库根目录 `LICENSE`）。MarkItDown 为微软 MIT 协议。Pandoc 使用 GPL 协议——重新分发时请查阅其许可证。