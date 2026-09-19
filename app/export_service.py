"""Markdown 导出服务。

把转换得到的 Markdown 写成 .md，或经 Pandoc 导出为 Word / HTML / PDF，
也可打包成 ZIP。支持时间戳前缀与重名避让。
"""

import shutil
import subprocess
import tempfile
import zipfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from app.settings import AppSettings


@dataclass
class ExportResult:
    """一次导出操作的结果。
    :param path: 实际写出的文件路径
    :param renamed: 是否因重名而改写了文件名
    :param original_name: 未避让前的目标文件名
    """

    path: str
    renamed: bool
    original_name: str


class ExportError(Exception):
    """导出失败（缺少 Pandoc、格式不支持或外部进程出错）。"""


def _project_root() -> Path:
    """返回仓库根目录。

    :return: ``export_service.py`` 所在包的上一级目录
    """
    return Path(__file__).resolve().parent.parent


def find_pandoc() -> Path | None:
    """查找捆绑或系统 PATH 中的 pandoc 可执行文件。

    :return: pandoc 路径；找不到时为 None
    """
    bundled = _project_root() / "bin" / "pandoc"
    if bundled.is_file() and bundled.stat().st_mode & 0o111:
        return bundled
    which = shutil.which("pandoc")
    return Path(which) if which else None


def format_extension(fmt: str) -> str:
    """把导出格式名规范成文件扩展名。
    :param fmt: 用户选择的格式（如 md / markdown / docx）
    :return: 不含点的扩展名
    """
    fmt = fmt.lower().strip()
    if fmt in {"md", "markdown"}:
        return "md"
    return fmt


def build_stem(settings: AppSettings, source_path: str) -> str:
    """按设置生成输出文件名主干（不含扩展名）。
    :param settings: 应用设置（是否加时间戳前缀）
    :param source_path: 源文件路径
    :return: 输出文件名主干
    """
    base = Path(source_path).stem or "output"
    if settings.timestamp_prefix:
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        return f"{stamp}-{base}"
    return base


def unique_output_path(directory: Path, stem: str, ext: str) -> tuple[Path, bool, str]:
    """在目录中生成不覆盖已有文件的输出路径。
    :param directory: 目标目录
    :param stem: 文件名主干
    :param ext: 扩展名（不含点）
    :return: (最终路径, 是否改名, 原始文件名)
    """
    original_name = f"{stem}.{ext}"
    candidate = directory / original_name
    if not candidate.exists():
        return candidate, False, original_name
    for i in range(1, 10_000):
        name = f"{stem}-{i}.{ext}"
        path = directory / name
        if not path.exists():
            return path, True, original_name
    name = f"{stem}-dup.{ext}"
    return directory / name, True, original_name


def resolve_save_dir(settings: AppSettings, save_dir: str | None = None) -> Path:
    """解析并创建导出目录。
    :param settings: 应用设置（回退目录）
    :param save_dir: 显式指定的目录；空则使用设置中的目录
    :return: 已存在的导出目录
    """
    directory = (save_dir or "").strip() or settings.resolved_save_dir()
    path = Path(directory).expanduser()
    path.mkdir(parents=True, exist_ok=True)
    return path


def _write_markdown(markdown: str, dest: Path) -> None:
    """将 Markdown 文本写入 UTF-8 文件。
    :param markdown: Markdown 正文
    :param dest: 目标文件路径
    :return: None
    """
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(markdown, encoding="utf-8")


def _write_with_pandoc(markdown: str, fmt: str, dest: Path) -> None:
    """通过 Pandoc 把 Markdown 转成指定格式并写入 ``dest``。
    :param markdown: Markdown 正文
    :param fmt: 目标格式（docx / html / pdf）
    :param dest: 输出文件路径
    :return: None
    :raises ExportError: 格式不支持、找不到 Pandoc 或转换失败
    """
    ext_map = {"docx": "docx", "html": "html", "pdf": "pdf"}
    if fmt not in ext_map:
        raise ExportError(f"Unsupported format: {fmt}")

    pandoc = find_pandoc()
    if pandoc is None:
        raise ExportError("Pandoc not found. Run scripts/fetch-pandoc.sh or install pandoc.")

    dest.parent.mkdir(parents=True, exist_ok=True)

    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".md", delete=False, encoding="utf-8"
    ) as tmp:
        tmp.write(markdown)
        tmp_path = Path(tmp.name)

    try:
        proc = subprocess.run(
            [
                str(pandoc),
                "-f",
                "markdown",
                "-t",
                fmt,
                "-o",
                str(dest),
                str(tmp_path),
            ],
            capture_output=True,
            text=True,
            check=False,
        )
    finally:
        tmp_path.unlink(missing_ok=True)

    if proc.returncode != 0:
        err = (proc.stderr or proc.stdout or "unknown error").strip()
        hint = ""
        if fmt == "pdf":
            hint = " For PDF you may need a PDF engine (wkhtmltopdf / pdflatex)."
        raise ExportError(f"Pandoc failed ({fmt}): {err}.{hint}")


def export_to_path(
    settings: AppSettings,
    source_path: str,
    markdown: str,
    fmt: str,
    output_path: str,
) -> ExportResult:
    """导出到用户指定的完整路径（不自动改名）。
    :param settings: 应用设置（当前导出路径本身不依赖设置）
    :param source_path: 源文件路径（保留参数以便调用方统一签名）
    :param markdown: Markdown 正文
    :param fmt: 导出格式
    :param output_path: 目标文件路径
    :return: 导出结果
    """
    dest = Path(output_path).expanduser()
    fmt = fmt.lower().strip()
    if fmt in {"md", "markdown"}:
        _write_markdown(markdown, dest)
    else:
        _write_with_pandoc(markdown, fmt, dest)
    return ExportResult(path=str(dest), renamed=False, original_name=dest.name)


def export_markdown(
    settings: AppSettings,
    source_path: str,
    markdown: str,
    save_dir: str | None = None,
) -> ExportResult:
    """把 Markdown 保存到目录，必要时自动改名避免覆盖。
    :param settings: 应用设置（时间戳、默认目录）
    :param source_path: 源文件路径，用于生成文件名
    :param markdown: Markdown 正文
    :param save_dir: 目标目录；空则使用设置中的目录
    :return: 导出结果
    """
    directory = resolve_save_dir(settings, save_dir)
    stem = build_stem(settings, source_path)
    out, renamed, original_name = unique_output_path(directory, stem, "md")
    _write_markdown(markdown, out)
    return ExportResult(path=str(out), renamed=renamed, original_name=original_name)


def export_with_format(
    settings: AppSettings,
    source_path: str,
    markdown: str,
    fmt: str,
    save_dir: str | None = None,
    output_path: str | None = None,
) -> ExportResult:
    """按格式导出；可指定完整路径或仅指定目录。
    :param settings: 应用设置
    :param source_path: 源文件路径
    :param markdown: Markdown 正文
    :param fmt: 导出格式
    :param save_dir: 未指定 ``output_path`` 时的目录
    :param output_path: 若给出则直接写到该路径
    :return: 导出结果
    """
    fmt = fmt.lower().strip()
    if output_path:
        return export_to_path(settings, source_path, markdown, fmt, output_path)
    if fmt in {"md", "markdown"}:
        return export_markdown(settings, source_path, markdown, save_dir)

    directory = resolve_save_dir(settings, save_dir)
    stem = build_stem(settings, source_path)
    out, renamed, original_name = unique_output_path(
        directory, stem, format_extension(fmt)
    )
    _write_with_pandoc(markdown, fmt, out)
    return ExportResult(path=str(out), renamed=renamed, original_name=original_name)


def unique_archive_name(used: set[str], stem: str, ext: str) -> str:
    """在 ZIP 内生成不重复的条目名，并登记到 ``used``。
    :param used: 已占用的条目名集合（会被原地修改）
    :param stem: 文件名主干
    :param ext: 扩展名（不含点）
    :return: ZIP 内相对路径名
    """
    original = f"{stem}.{ext}"
    candidate = original
    index = 1
    while candidate in used:
        candidate = f"{stem}-{index}.{ext}"
        index += 1
        if index > 10_000:
            candidate = f"{stem}-dup.{ext}"
            break
    used.add(candidate)
    return candidate


def export_zip(
    settings: AppSettings,
    files: list[tuple[str, str]],
    output_path: str,
) -> ExportResult:
    """把多份 Markdown 打成一个 ZIP。
    :param settings: 应用设置（条目命名）
    :param files: ``(源路径, Markdown 正文)`` 列表
    :param output_path: ZIP 输出路径
    :return: 导出结果
    """
    dest = Path(output_path).expanduser()
    dest.parent.mkdir(parents=True, exist_ok=True)
    used: set[str] = set()
    renamed = False
    with zipfile.ZipFile(dest, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for source_path, markdown in files:
            stem = build_stem(settings, source_path)
            name = unique_archive_name(used, stem, "md")
            if name != f"{stem}.md":
                renamed = True
            archive.writestr(name, markdown)
    return ExportResult(path=str(dest), renamed=renamed, original_name=dest.name)
