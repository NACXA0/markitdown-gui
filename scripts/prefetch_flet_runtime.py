#!/usr/bin/env python3
"""把 Flet 构建依赖的 GitHub 文件预先放进 ~/.flet/cache。

`flet build` 要下载 python-build 的 manifest.json；随后 CMake 再下载
python-linux-dart / python-windows-for-dart 和 dart_bridge。这些地址在
GitHub 上。国内网络常见超时（WinError 10060）或 SSL connect error。
缓存文件已存在且非空时，Flet 和 CMake 都会跳过下载。

版本钉在与 Flet 1.0.0 一起发布的 python-build 20260908 / dart-bridge 1.9.0。
"""

from __future__ import annotations

import json
import os
import platform
import shutil
import ssl
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

PYTHON_BUILD_DATE = "20260908"
PYTHON_SHORT = "3.14"
PYTHON_FULL_FALLBACK = "3.14.7"
DART_BRIDGE_VERSION = "1.9.0"
FLET_VERSION_FALLBACK = "1.0.0"

# 先走镜像，再回源。镜像不可达时尽快失败，避免把能直连的机器拖住。
MIRROR_PREFIXES = (
    "https://ghfast.top/",
    "https://gh-proxy.com/",
)
CONNECT_TIMEOUT_S = 20
READ_TIMEOUT_S = 180


def cache_root() -> Path:
    raw = os.environ.get("FLET_CACHE_DIR")
    root = Path(raw).expanduser() if raw else Path.home() / ".flet" / "cache"
    return root


def host_kind() -> tuple[str, str]:
    """返回 (os, arch_tag)。arch_tag 与 CMake 的 CMAKE_HOST_SYSTEM_PROCESSOR 对齐。"""
    system = platform.system().lower()
    machine = platform.machine().lower()
    if machine in {"amd64", "x86_64"}:
        arch = "x86_64"
    elif machine in {"arm64", "aarch64"}:
        arch = "aarch64"
    else:
        raise SystemExit(f"不支持的 CPU 架构: {platform.machine()}")
    if system == "windows":
        return "windows", arch
    if system == "linux":
        return "linux", arch
    raise SystemExit(f"prefetch 目前只覆盖 Linux 与 Windows，当前系统是 {platform.system()}")


def flet_version() -> str:
    try:
        import flet.version as version_mod
    except Exception:
        return FLET_VERSION_FALLBACK
    for name in ("flet_version", "version"):
        value = getattr(version_mod, name, None)
        if isinstance(value, str) and value:
            return value.lstrip("v")
    return FLET_VERSION_FALLBACK


def python_build_date() -> str:
    try:
        from flet_cli.utils.python_versions import PYTHON_BUILD_RELEASE_DATE
    except Exception:
        return PYTHON_BUILD_DATE
    if isinstance(PYTHON_BUILD_RELEASE_DATE, str) and PYTHON_BUILD_RELEASE_DATE:
        return PYTHON_BUILD_RELEASE_DATE
    return PYTHON_BUILD_DATE


def urls_for(github_url: str) -> list[str]:
    mirrored = [prefix + github_url for prefix in MIRROR_PREFIXES]
    return mirrored + [github_url]


def download(github_url: str, dest: Path) -> None:
    if dest.is_file() and dest.stat().st_size > 0:
        print(f"==> 已缓存 {dest}")
        return
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".tmp")
    errors: list[str] = []
    for url in urls_for(github_url):
        print(f"==> 下载 {url}")
        try:
            if shutil.which("curl"):
                tmp.unlink(missing_ok=True)
                subprocess.run(
                    [
                        "curl",
                        "-L",
                        "--fail",
                        "--connect-timeout",
                        str(CONNECT_TIMEOUT_S),
                        "--retry",
                        "2",
                        "--retry-delay",
                        "2",
                        "-o",
                        str(tmp),
                        url,
                    ],
                    check=True,
                )
            else:
                request = urllib.request.Request(url, headers={"User-Agent": "markitdown-gui-prefetch"})
                with urllib.request.urlopen(request, timeout=READ_TIMEOUT_S) as resp, tmp.open("wb") as out:
                    while True:
                        chunk = resp.read(1024 * 256)
                        if not chunk:
                            break
                        out.write(chunk)
            if not tmp.is_file() or tmp.stat().st_size <= 0:
                raise OSError("空文件")
            tmp.replace(dest)
            print(f"==> 已写入 {dest} ({dest.stat().st_size} bytes)")
            return
        except (subprocess.CalledProcessError, urllib.error.URLError, TimeoutError, OSError, ssl.SSLError) as exc:
            errors.append(f"{url}: {exc}")
            tmp.unlink(missing_ok=True)
            print(f"    失败: {exc}", file=sys.stderr)
    raise SystemExit(
        "无法下载构建依赖。可手动把文件放到缓存路径后重试。\n"
        + "\n".join(errors)
        + f"\n目标: {dest}\n源: {github_url}"
    )


def python_full_version(manifest_path: Path) -> str:
    try:
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
        full = data["pythons"][PYTHON_SHORT]["full_version"]
    except (OSError, KeyError, json.JSONDecodeError, TypeError) as exc:
        print(f"==> 无法从 manifest 读取 {PYTHON_SHORT} 全版本，改用 {PYTHON_FULL_FALLBACK}: {exc}", file=sys.stderr)
        return PYTHON_FULL_FALLBACK
    if not isinstance(full, str) or not full:
        return PYTHON_FULL_FALLBACK
    return full


def main() -> None:
    os_name, arch = host_kind()
    root = cache_root()
    date = python_build_date()
    flet_ver = flet_version()
    print(f"==> 预取 Flet 运行时: os={os_name} arch={arch} python-build={date} flet={flet_ver}")
    print(f"==> 缓存目录: {root}")

    manifest = root / "python-build" / f"manifest-{date}.json"
    download(
        f"https://github.com/flet-dev/python-build/releases/download/{date}/manifest.json",
        manifest,
    )
    full = python_full_version(manifest)
    pb = root / "python-build" / f"v{full}-{date}"
    db = root / "dart-bridge" / f"v{DART_BRIDGE_VERSION}"

    if os_name == "linux":
        download(
            f"https://github.com/flet-dev/python-build/releases/download/{date}/python-linux-dart-{full}-{arch}.tar.gz",
            pb / f"python-linux-dart-{full}-{arch}.tar.gz",
        )
        download(
            f"https://github.com/flet-dev/dart-bridge/releases/download/v{DART_BRIDGE_VERSION}/libdart_bridge-linux-{arch}.so",
            db / f"libdart_bridge-linux-{arch}.so",
        )
    else:
        if arch != "x86_64":
            raise SystemExit("Windows 构建目前只提供 x86_64 的 python-build / dart_bridge 预构建包。")
        download(
            f"https://github.com/flet-dev/python-build/releases/download/{date}/python-windows-for-dart-{full}.zip",
            pb / f"python-windows-for-dart-{full}.zip",
        )
        download(
            f"https://github.com/flet-dev/dart-bridge/releases/download/v{DART_BRIDGE_VERSION}/dart_bridge-windows-x86_64.dll",
            db / "dart_bridge-windows-x86_64.dll",
        )
        download(
            f"https://github.com/flet-dev/dart-bridge/releases/download/v{DART_BRIDGE_VERSION}/dart_bridge_d-windows-x86_64.dll",
            db / "dart_bridge_d-windows-x86_64.dll",
        )

    download(
        f"https://github.com/flet-dev/flet/releases/download/v{flet_ver}/flet-build-template.zip",
        root / "build-template" / f"v{flet_ver}" / "flet-build-template.zip",
    )
    print("==> 预取完成。接着执行 flet build；已缓存的文件不会再次从 GitHub 下载。")


if __name__ == "__main__":
    main()
