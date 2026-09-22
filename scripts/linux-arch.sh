#!/usr/bin/env bash
# 供其他打包脚本 source：根据 uname -m 设置 deb / AppImage / Flutter 架构名。
# 用法（在 scripts/*.sh 内）：
#   # shellcheck source=linux-arch.sh
#   source "$(cd "$(dirname "$0")" && pwd)/linux-arch.sh"
#   detect_linux_arch

detect_linux_arch() {
  case "$(uname -m)" in
    x86_64|amd64)
      HOST_MACHINE="x86_64"
      DEB_ARCH="amd64"
      APPIMAGE_ARCH="x86_64"
      FLUTTER_LINUX_ARCH="x64"
      APPIMAGETOOL_ARCH="x86_64"
      # `file` 对 ELF 的描述片段
      ELF_ARCH_PATTERN='x86-64|x86_64'
      ;;
    aarch64|arm64)
      HOST_MACHINE="aarch64"
      DEB_ARCH="arm64"
      APPIMAGE_ARCH="aarch64"
      FLUTTER_LINUX_ARCH="arm64"
      APPIMAGETOOL_ARCH="aarch64"
      ELF_ARCH_PATTERN='ARM aarch64|aarch64'
      ;;
    *)
      echo "Unsupported Linux architecture: $(uname -m)" >&2
      echo "Supported: x86_64 (amd64), aarch64 (arm64). Cross-building is not supported." >&2
      return 1
      ;;
  esac
}

# 校验可执行文件是否与当前宿主架构一致。
verify_elf_arch() {
  local bin="$1"
  local info
  if [[ ! -e "$bin" ]]; then
    echo "Missing binary: $bin" >&2
    return 1
  fi
  info="$(file -b "$bin" 2>/dev/null || true)"
  if ! grep -Eqi "$ELF_ARCH_PATTERN" <<<"$info"; then
    echo "Architecture mismatch: $bin" >&2
    echo "  file says: $info" >&2
    echo "  host expects: $HOST_MACHINE ($ELF_ARCH_PATTERN)" >&2
    return 1
  fi
}

# 回退用的 Flutter release bundle 路径（Flet 有时留在 build/flutter 下）。
flutter_linux_bundle_path() {
  local root="${1:-.}"
  echo "$root/build/flutter/build/linux/${FLUTTER_LINUX_ARCH}/release/bundle"
}

deb_package_basename() {
  local pkg="${1:?}"
  local version="${2:?}"
  echo "${pkg}_${version}_${DEB_ARCH}"
}

appimage_basename() {
  echo "MarkItDown_GUI-${APPIMAGE_ARCH}.AppImage"
}

# 桌面目录改名（如 桌面→Desktop）后，Flet 会把旧绝对路径写进
# build/flutter/pubspec.yaml；此处按当前仓库根目录重写 path 依赖。
sanitize_flutter_pubspec_paths() {
  local root="${1:?}"
  local pubspec="$root/build/flutter/pubspec.yaml"
  local packages="$root/build/flutter-packages"
  [[ -f "$pubspec" && -d "$packages" ]] || return 0
  python3 - "$pubspec" "$packages" <<'PY'
import pathlib, sys, re
pubspec = pathlib.Path(sys.argv[1])
packages = pathlib.Path(sys.argv[2]).resolve()
text = pubspec.read_text(encoding="utf-8")
# path: "/abs/.../flutter-packages/<name>" 或 Unicode 转义形式
pat = re.compile(
    r'(^\s+\w+:\s*\n\s+path:\s*)("(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\')',
    re.M,
)

def repl(m: re.Match[str]) -> str:
    raw = m.group(2)[1:-1]
    try:
        path = bytes(raw, "utf-8").decode("unicode_escape")
    except Exception:
        path = raw
    p = pathlib.Path(path)
    # 仅处理指向 flutter-packages 的本地 path 依赖
    try:
        name = p.name
        candidate = packages / name
        if candidate.is_dir() and (candidate / "pubspec.yaml").is_file():
            if not p.exists() or p.resolve() != candidate.resolve():
                return f'{m.group(1)}"{candidate.as_posix()}"'
    except Exception:
        pass
    return m.group(0)

new = pat.sub(repl, text)
if new != text:
    pubspec.write_text(new, encoding="utf-8")
    print(f"==> Rewrote stale Flutter path deps in {pubspec}")
PY
}

# 桌面打包不需要 Android SDK；清掉本机 ANDROID_* 以免 flutter doctor / 钩子误检。
flet_build_linux_env() {
  env -u ANDROID_HOME -u ANDROID_SDK_ROOT "$@"
}
