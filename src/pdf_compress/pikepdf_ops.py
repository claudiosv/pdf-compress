"""pikepdf-backed operations: structural checks, repair, flattening, linearization."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pikepdf

from pdf_compress.errors import PipelineError
from pdf_compress.reporting import console, err_console
from pdf_compress.util import stage_log_path


def pikepdf_check_encrypted(path: Path) -> bool:
    """True if the PDF requires a password to open (qpdf --requires-password).

    Any other failure (corruption, etc.) is not this check's concern — it is
    left for the syntax-check stage to report, matching qpdf's own CLI
    behavior where --requires-password only reports "yes" on exit 0.
    """
    try:
        with pikepdf.open(path):
            pass
    except pikepdf.PasswordError:
        return True
    except pikepdf.PdfError:
        return False
    return False


def pikepdf_check_syntax(path: Path) -> list[str]:
    """Structural validation (qpdf --check --warning-exit-0 equivalent).

    Raises ``pikepdf.PdfError`` for unrecoverable corruption; returns a
    (possibly empty) list of warning strings for anything less severe.
    """
    with pikepdf.open(path) as pdf:
        return pdf.check_pdf_syntax()


def pikepdf_flatten_annotations(src: Path, dst: Path) -> list[str]:
    with pikepdf.open(src) as pdf:
        pdf.generate_appearance_streams()
        pdf.flatten_annotations(mode="all")
        pdf.save(dst)
    return []


def pikepdf_repair(src: Path, dst: Path) -> list[str]:
    with pikepdf.open(src) as pdf:
        warnings = [str(w) for w in pdf.get_warnings()]
        pdf.save(dst, object_stream_mode=pikepdf.ObjectStreamMode.generate)
    return warnings


def pikepdf_linearize(src: Path, dst: Path) -> list[str]:
    with pikepdf.open(src) as pdf:
        pdf.save(dst, linearize=True)
    return []


def run_pikepdf_stage(
    name: str,
    fn: Callable[[], list[str]],
    work_dir: Path,
    *,
    ui_enabled: bool,
    verbose: bool,
) -> list[str]:
    """Run a pikepdf-backed operation, reporting progress via a rich spinner.

    ``fn`` performs the operation and returns diagnostic messages (may be
    empty); it should raise ``pikepdf.PdfError`` on failure.
    """
    log_file = stage_log_path(work_dir, name)

    def _execute() -> list[str]:
        try:
            messages = fn()
        except pikepdf.PdfError as exc:
            log_file.write_text(str(exc))
            raise
        log_file.write_text("\n".join(messages))
        return messages

    if not ui_enabled or verbose:
        err_console.print(f"{name}...")
        try:
            messages = _execute()
        except pikepdf.PdfError as exc:
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
        except pikepdf.PdfError as exc:
            console.print(f"[bold red]✗[/bold red] {name}")
            raise PipelineError(f"{name} failed: {exc}", log_file) from exc
    console.print(f"[bold green]✓[/bold green] {name}")
    return messages
