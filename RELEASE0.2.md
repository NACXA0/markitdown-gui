# MarkItDown GUI 0.2

**版本：** 0.2  
**日期：** 2026-09-28  
**平台：** Linux x86_64（amd64）／WindowsX64

### MarkItDown GUI 是 [Microsoft MarkItDown](https://github.com/microsoft/markitdown) 的桌面前端。把 PDF、Office、图片等文件转成 Markdown，在窗口里预览，再导出成 Markdown、Word、HTML 或 PDF。

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


## 许可

本 GUI 采用 Apache License 2.0（见仓库 `LICENSE`），没有附加商业条款。MarkItDown 本体为 Microsoft MIT。随包 Pandoc 为 GPL。

## 反馈

问题与建议请提到 <https://github.com/NACXA0/markitdown-gui/issues>。说明系统版本、安装方式（deb / AppImage），以及复现步骤。
