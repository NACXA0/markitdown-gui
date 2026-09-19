from __future__ import annotations

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
    path: str
    renamed: bool
    original_name: str


class ExportError(Exception):
    pass


def _project_root() -> Path:
    return Path(__file__).resolve().parent.parent


def find_pandoc() -> Path | None:
    bundled = _project_root() / "bin" / "pandoc"
    if bundled.is_file() and bundled.stat().st_mode & 0o111:
        return bundled
    which = shutil.which("pandoc")
    return Path(which) if which else None


def format_extension(fmt: str) -> str:
    fmt = fmt.lower().strip()
    if fmt in {"md", "markdown"}:
        return "md"
    return fmt


def build_stem(settings: AppSettings, source_path: str) -> str:
    base = Path(source_path).stem or "output"
    if settings.timestamp_prefix:
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        return f"{stamp}-{base}"
    return base


def unique_output_path(directory: Path, stem: str, ext: str) -> tuple[Path, bool, str]:
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
    directory = (save_dir or "").strip() or settings.resolved_save_dir()
    path = Path(directory).expanduser()
    path.mkdir(parents=True, exist_ok=True)
    return path


def _write_markdown(markdown: str, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(markdown, encoding="utf-8")


def _write_with_pandoc(markdown: str, fmt: str, dest: Path) -> None:
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
