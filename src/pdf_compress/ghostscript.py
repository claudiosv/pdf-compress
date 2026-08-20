"""Ghostscript integration: in-process library bindings and argument building."""

from __future__ import annotations

import os
import re
import shutil
import sys
from pathlib import Path
from typing import IO, TYPE_CHECKING

from rich.progress import (
    BarColumn,
    MofNCompleteColumn,
    Progress,
    SpinnerColumn,
    TaskID,
    TextColumn,
    TimeElapsedColumn,
)

from pdf_compress.errors import PdfCompressError, PipelineError
from pdf_compress.reporting import console, err_console
from pdf_compress.util import stage_log_path

if TYPE_CHECKING:
    import types

PAGE_LINE_RE = re.compile(r"^Page (\d+)$")

_GS_MODULE: types.ModuleType | None = None


def _prime_ghostscript_library_path() -> None:
    """Point the dynamic linker at libgs before importing the ghostscript
    bindings, since ctypes' default search often misses Homebrew installs."""
    gs_path = shutil.which("gs")
    if not gs_path:
        return
    lib_dir = Path(gs_path).resolve().parent.parent / "lib"
    if not lib_dir.is_dir():
        return
    var = (
        "DYLD_FALLBACK_LIBRARY_PATH" if sys.platform == "darwin" else "LD_LIBRARY_PATH"
    )
    existing = os.environ.get(var, "")
    if str(lib_dir) in existing.split(":"):
        return
    os.environ[var] = f"{lib_dir}:{existing}" if existing else str(lib_dir)


def ghostscript_module() -> types.ModuleType:
    """Import (and cache) the ghostscript library bindings, priming the
    dynamic-linker search path first so Homebrew/local installs are found."""
    global _GS_MODULE
    if _GS_MODULE is not None:
        return _GS_MODULE
    _prime_ghostscript_library_path()
    try:
        import ghostscript as gs_module
    except (ImportError, RuntimeError, OSError) as exc:
        raise PdfCompressError(
            "Could not load the Ghostscript library (libgs). Install "
            f"Ghostscript (e.g. 'brew install ghostscript'). Details: {exc}"
        ) from exc
    _GS_MODULE = gs_module
    return gs_module


class _GsPageWriter:
    """Ghostscript stdout sink: parses 'Page N' lines to drive a rich
    progress task (if given), tees to stderr when verbose, and always
    mirrors everything into the stage log file."""

    def __init__(
        self,
        log: IO[bytes],
        *,
        progress: Progress | None = None,
        task_id: TaskID | None = None,
        verbose: bool = False,
    ) -> None:
        self._log = log
        self._progress = progress
        self._task_id = task_id
        self._verbose = verbose
        self._pending = ""
        self._last_page = 0

    def write(self, data: bytes | str) -> None:
        if isinstance(data, str):
            data = data.encode("utf-8", errors="replace")
        self._log.write(data)
        if self._verbose:
            sys.stderr.buffer.write(data)
        if self._progress is None:
            return
        self._pending += data.decode("utf-8", errors="replace")
        if "\n" not in self._pending:
            return
        complete, _, remainder = self._pending.rpartition("\n")
        self._pending = remainder
        for line in complete.split("\n"):
            match = PAGE_LINE_RE.match(line)
            if match:
                page = int(match.group(1))
                if page > self._last_page:
                    self._last_page = page
                    self._progress.update(self._task_id, completed=page)

    def flush(self) -> None:
        self._log.flush()
        if self._verbose:
            sys.stderr.buffer.flush()


class _LogWriter:
    """Plain stdio sink: mirrors output into the stage log (and stderr)."""

    def __init__(self, log: IO[bytes], *, verbose: bool = False) -> None:
        self._log = log
        self._verbose = verbose

    def write(self, data: bytes | str) -> None:
        if isinstance(data, str):
            data = data.encode("utf-8", errors="replace")
        self._log.write(data)
        if self._verbose:
            sys.stderr.buffer.write(data)

    def flush(self) -> None:
        self._log.flush()
        if self._verbose:
            sys.stderr.buffer.flush()


def run_ghostscript_lib(
    name: str,
    args: list[str],
    work_dir: Path,
    *,
    ui_enabled: bool,
    verbose: bool,
    total_pages: int | None = None,
) -> None:
    """Run Ghostscript in-process via the ghostscript library bindings.

    Shows a live rich progress bar keyed off 'Page N' stdout lines when
    ``total_pages`` is known; otherwise behaves like a normal spinner stage.
    """
    gs_module = ghostscript_module()
    log_file = stage_log_path(work_dir, name)

    def _execute(
        progress: Progress | None = None, task_id: TaskID | None = None
    ) -> None:
        with log_file.open("wb") as log:
            stdout_writer = _GsPageWriter(
                log, progress=progress, task_id=task_id, verbose=verbose
            )
            stderr_writer = _LogWriter(log, verbose=verbose)
            with gs_module.Ghostscript(
                "gs", *args, stdout=stdout_writer, stderr=stderr_writer
            ):
                pass

    show_bar = (
        ui_enabled and not verbose and total_pages is not None and total_pages > 0
    )

    if not ui_enabled or verbose:
        err_console.print(f"{name}...")
        try:
            _execute()
        except gs_module.GhostscriptError as exc:
            err_console.print(f"{name}: failed")
            raise PipelineError(f"{name} failed: {exc}", log_file) from exc
        err_console.print(f"{name}: done")
        return

    if show_bar:
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            MofNCompleteColumn(),
            TimeElapsedColumn(),
            console=console,
            transient=False,
        ) as progress:
            task_id = progress.add_task(name, total=total_pages)
            try:
                _execute(progress, task_id)
            except gs_module.GhostscriptError as exc:
                progress.update(task_id, description=f"[red]{name}[/red]")
                raise PipelineError(f"{name} failed: {exc}", log_file) from exc
            progress.update(
                task_id, completed=total_pages, description=f"[green]{name}[/green]"
            )
        return

    with console.status(f"[bold cyan]{name}...", spinner="dots"):
        try:
            _execute()
        except gs_module.GhostscriptError as exc:
            console.print(f"[bold red]✗[/bold red] {name}")
            raise PipelineError(f"{name} failed: {exc}", log_file) from exc
    console.print(f"[bold green]✓[/bold green] {name}")


def build_gs_args(
    *,
    in_file: Path,
    out_file: Path,
    compat: str,
    quality: str,
    pdfa_level: str,
    convert_color: bool,
    icc_profile: Path | None,
    pdfa_def: Path | None,
) -> list[str]:
    args = [
        "-sDEVICE=pdfwrite",
        f"-dCompatibilityLevel={compat}",
        f"-dPDFSETTINGS=/{quality}",
        "-dPreserveAnnots=true",
        "-dNOPAUSE",
        "-dBATCH",
    ]
    if pdfa_level != "none":
        args += [
            f"-dPDFA={pdfa_level}",
            "-dPDFACompatibilityPolicy=2",
            "-sColorConversionStrategy=RGB",
            "-dProcessColorModel=/DeviceRGB",
            f"--permit-file-read={icc_profile}",
        ]
    elif convert_color:
        args += ["-sColorConversionStrategy=RGB", "-dProcessColorModel=/DeviceRGB"]

    args.append(f"-sOutputFile={out_file}")
    if pdfa_level != "none":
        assert pdfa_def is not None
        args.append(str(pdfa_def))
    args.append(str(in_file))
    return args


def build_ps2pdf_args(*, in_file: Path, out_file: Path) -> list[str]:
    """Replicate Ghostscript's own ps2pdfwr/ps2pdf14 wrapper scripts."""
    return [
        "-P-",
        "-dSAFER",
        "-q",
        "-dNOPAUSE",
        "-dBATCH",
        "-sDEVICE=pdfwrite",
        "-sstdout=%stderr",
        "-dCompatibilityLevel=1.4",
        "-dWriteXRefStm=false",
        "-dWriteObjStms=false",
        f"-sOutputFile={out_file}",
        str(in_file),
    ]
