#!/usr/bin/env python3
"""把官方 Pandoc Windows x64 二进制放进 Flet Windows 包的 app/bin/。

下载先走 ghfast.top、gh-proxy.com，再回源 GitHub（与 prefetch_flet_runtime 相同）。
须在 Windows 上运行；产物为 build/windows/app/bin/pandoc.exe。
"""

from __future__ import annotations

import os
import shutil
import ssl
import sys
import tempfile
import urllib.error
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEST = ROOT / "build" / "windows" / "app" / "bin" / "pandoc.exe"
PANDOC_VERSION = os.environ.get("PANDOC_VERSION", "3.6.4")
ARCHIVE = f"pandoc-{PANDOC_VERSION}-windows-x86_64.zip"
GITHUB_URL = (
    f"https://github.com/jgm/pandoc/releases/download/"
    f"{PANDOC_VERSION}/{ARCHIVE}"
)
MIRROR_PREFIXES = (
    "https://ghfast.top/",
    "https://gh-proxy.com/",
)
CONNECT_TIMEOUT_S = 20
READ_TIMEOUT_S = 180


def urls_for(github_url: str) -> list[str]:
    return [prefix + github_url for prefix in MIRROR_PREFIXES] + [github_url]


def download(github_url: str, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".tmp")
    errors: list[str] = []
    for url in urls_for(github_url):
        print(f"==> 下载 {url}")
        try:
            if shutil.which("curl"):
                import subprocess

                subprocess.run(
                    [
                        "curl",
                        "-fL",
                        "--connect-timeout",
                        str(CONNECT_TIMEOUT_S),
                        "--max-time",
                        str(READ_TIMEOUT_S),
                        "-o",
                        str(tmp),
                        url,
                    ],
                    check=True,
                )
            else:
                ctx = ssl.create_default_context()
                with urllib.request.urlopen(
                    url, timeout=READ_TIMEOUT_S, context=ctx
                ) as resp:
                    tmp.write_bytes(resp.read())
            if tmp.is_file() and tmp.stat().st_size > 0:
                tmp.replace(dest)
                return
            errors.append(f"{url}: empty download")
        except (urllib.error.URLError, OSError, Exception) as exc:
            errors.append(f"{url}: {exc}")
            if tmp.is_file():
                tmp.unlink(missing_ok=True)
    raise SystemExit("Pandoc 下载失败:\n  " + "\n  ".join(errors))


def main() -> None:
    if DEST.is_file() and DEST.stat().st_size > 0:
        print(f"==> Pandoc 已在包内: {DEST}")
        return

    if not (ROOT / "build" / "windows").is_dir():
        raise SystemExit(f"缺少 build\\windows，请先构建 Windows 客户端: {ROOT}")

    with tempfile.TemporaryDirectory(prefix="pandoc-win-") as td:
        td_path = Path(td)
        archive = td_path / ARCHIVE
        download(GITHUB_URL, archive)
        print(f"==> 解压 {archive.name}")
        with zipfile.ZipFile(archive) as zf:
            names = [n for n in zf.namelist() if n.endswith("pandoc.exe")]
            if not names:
                raise SystemExit(f"{ARCHIVE} 内未找到 pandoc.exe")
            # 优先取路径最短的（通常为 pandoc-VERSION/pandoc.exe）
            member = sorted(names, key=len)[0]
            extracted = zf.extract(member, td_path)
        src = Path(extracted)
        DEST.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, DEST)
    print(f"==> Pandoc 已写入: {DEST}")


if __name__ == "__main__":
    main()
    sys.exit(0)
