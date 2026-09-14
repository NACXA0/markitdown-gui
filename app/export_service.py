from __future__ import annotations

import shutil
import subprocess
import tempfile
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


def export_markdown(
    settings: AppSettings,
    source_path: str,
    markdown: str,
    save_dir: str | None = None,
) -> ExportResult:
    directory = resolve_save_dir(settings, save_dir)
    stem = build_stem(settings, source_path)
    out, renamed, original_name = unique_output_path(directory, stem, "md")
    out.write_text(markdown, encoding="utf-8")
    return ExportResult(path=str(out), renamed=renamed, original_name=original_name)


def export_with_format(
    settings: AppSettings,
    source_path: str,
    markdown: str,
    fmt: str,
    save_dir: str | None = None,
) -> ExportResult:
    fmt = fmt.lower().strip()
    if fmt in {"md", "markdown"}:
        return export_markdown(settings, source_path, markdown, save_dir)

    ext_map = {"docx": "docx", "html": "html", "pdf": "pdf"}
    if fmt not in ext_map:
        raise ExportError(f"Unsupported format: {fmt}")

    pandoc = find_pandoc()
    if pandoc is None:
        raise ExportError("Pandoc not found. Run scripts/fetch-pandoc.sh or install pandoc.")

    directory = resolve_save_dir(settings, save_dir)
    stem = build_stem(settings, source_path)
    out, renamed, original_name = unique_output_path(directory, stem, ext_map[fmt])

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
                str(out),
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

    return ExportResult(path=str(out), renamed=renamed, original_name=original_name)
