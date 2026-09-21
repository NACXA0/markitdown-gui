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
