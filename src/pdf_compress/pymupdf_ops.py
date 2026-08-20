"""PyMuPDF-backed lossless structural/stream optimization."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pymupdf

from pdf_compress.errors import PipelineError
from pdf_compress.reporting import console, err_console
from pdf_compress.util import stage_log_path


def pymupdf_clean(src: Path, dst: Path, *, drop_structure: bool) -> list[str]:
    """Lossless structural/stream optimization.

    Equivalent to
    ``mutool clean -gggg -z -f -i -Z -t -m -e 100 --structure=keep|drop``.
    """
    with pymupdf.open(src) as doc:
        if drop_structure:
            catalog_xref = doc.pdf_catalog()
            doc.xref_set_key(catalog_xref, "StructTreeRoot", "null")
            doc.xref_set_key(catalog_xref, "MarkInfo", "null")
        doc.save(
            dst,
            garbage=4,
            deflate=True,
            deflate_fonts=True,
            deflate_images=True,
            use_objstms=True,
            compression_effort=100,
            pretty=False,
            preserve_metadata=True,
        )
    return []


def run_pymupdf_stage(
    name: str,
    fn: Callable[[], list[str]],
    work_dir: Path,
    *,
    ui_enabled: bool,
    verbose: bool,
) -> list[str]:
    """Run a PyMuPDF-backed operation, reporting progress via a rich spinner.

    ``fn`` performs the operation and returns diagnostic messages (may be
    empty); it should raise ``RuntimeError`` (pymupdf's exception base) on
    failure.
    """
    log_file = stage_log_path(work_dir, name)

    def _execute() -> list[str]:
        try:
            messages = fn()
        except RuntimeError as exc:
            log_file.write_text(str(exc))
            raise
        log_file.write_text("\n".join(messages))
        return messages

    if not ui_enabled or verbose:
        err_console.print(f"{name}...")
        try:
            messages = _execute()
        except RuntimeError as exc:
            err_console.print(f"{name}: failed")
            raise PipelineError(f"{name} failed: {exc}", log_file) from exc
        if verbose:
            for line in messages:
                err_console.print(line, style="dim", markup=False)
        err_console.print(f"{name}: done")
        return messages

    with console.status(f"[bold cyan]{name}...", spinner="dots"):
        try:
            messages = _execute()
        except RuntimeError as exc:
            console.print(f"[bold red]✗[/bold red] {name}")
            raise PipelineError(f"{name} failed: {exc}", log_file) from exc
    console.print(f"[bold green]✓[/bold green] {name}")
    return messages
