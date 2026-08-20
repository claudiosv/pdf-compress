"""Pipeline orchestration: config resolution, stage sequencing, PDF/A validation."""

from __future__ import annotations

import shutil
import signal
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

import pikepdf

from pdf_compress.errors import PdfCompressError, UsageError
from pdf_compress.ghostscript import (
    build_gs_args,
    build_ps2pdf_args,
    ghostscript_module,
    run_ghostscript_lib,
)
from pdf_compress.models import Config, Mode, PipelineResult
from pdf_compress.pikepdf_ops import (
    pikepdf_check_encrypted,
    pikepdf_check_syntax,
    pikepdf_flatten_annotations,
    pikepdf_linearize,
    pikepdf_repair,
    run_pikepdf_stage,
)
from pdf_compress.pymupdf_ops import pymupdf_clean, run_pymupdf_stage
from pdf_compress.reporting import console, err_console, show_stage_log
from pdf_compress.util import (
    create_pdfa_definition,
    file_bytes,
    find_icc_profile,
    page_count,
    require_command,
)


@dataclass
class RunState:
    """Tracks live state so signal handlers can clean up mid-run."""

    work_dir: Path | None = None
    running_proc: subprocess.Popen | None = None


STATE = RunState()


def install_signal_handlers() -> None:
    def _handle(code: int):
        def handler(_signum: int, _frame: object) -> None:
            if STATE.running_proc is not None:
                STATE.running_proc.kill()
            sys.exit(code)

        return handler

    signal.signal(signal.SIGINT, _handle(130))
    signal.signal(signal.SIGTERM, _handle(143))
    signal.signal(signal.SIGHUP, _handle(129))


def resolve_config(cfg: Config) -> tuple[Path, Path]:
    input_real = cfg.input_file.resolve()
    if not input_real.is_file():
        raise UsageError(f"Input file '{cfg.input_file}' was not found.")

    if cfg.output_file is not None:
        output_real = cfg.output_file.resolve()
    else:
        is_pdf = input_real.suffix.lower() == ".pdf"
        stem = input_real.stem if is_pdf else input_real.name
        output_real = input_real.with_name(f"{stem}_compressed.pdf")

    if input_real == output_real:
        raise UsageError("Input and output must be different files.")

    return input_real, output_real


def validate_pdfa_constraints(cfg: Config) -> str:
    if cfg.pdfa_level == "none":
        if cfg.icc_profile:
            raise UsageError("--icc-profile is only used with --pdfa.")
        return cfg.compat

    if cfg.mode == Mode.lossless:
        raise UsageError("PDF/A output requires a Ghostscript mode.")
    if not cfg.convert_color:
        raise UsageError("--no-convert-color cannot be used with PDF/A.")
    if cfg.drop_structure:
        raise UsageError("--drop-structure cannot be used with PDF/A.")

    required_compat = "1.4" if cfg.pdfa_level == "1" else "1.7"
    if cfg.compat_explicit and cfg.compat != required_compat:
        raise UsageError(
            f"PDF/A-{cfg.pdfa_level} requires compatibility {required_compat}."
        )
    return required_compat


def check_required_commands(cfg: Config) -> None:
    require_command("pdfinfo", "Install Poppler.")

    if cfg.mode in (Mode.compress, Mode.repair, Mode.ps2pdf_recovery):
        ghostscript_module()  # raises PdfCompressError if libgs can't be loaded

    if cfg.pdfa_level != "none":
        require_command(
            "verapdf",
            "Install veraPDF; PDF/A output is not accepted without final validation.",
        )


def run_pipeline(cfg: Config, ui_enabled: bool = False) -> PipelineResult | None:
    """Run the full compression pipeline.

    Returns ``None`` for a dry run, otherwise a ``PipelineResult`` describing
    the outcome (``installed=False`` if ``only_if_smaller`` rejected the
    candidate).
    """
    input_real, output_real = resolve_config(cfg)
    required_compat = validate_pdfa_constraints(cfg)
    cfg.compat = required_compat

    if cfg.dry_run:
        return None

    if output_real.exists() and not cfg.force:
        if sys.stdin.isatty() and ui_enabled:
            import typer

            replace = typer.confirm(
                f"File '{output_real}' already exists. Replace it?", default=False
            )
            if not replace:
                raise PdfCompressError(
                    "Output exists; use --force in non-interactive runs."
                )
        else:
            raise PdfCompressError(
                "Output exists; use --force in non-interactive runs."
            )

    check_required_commands(cfg)

    output_real.parent.mkdir(parents=True, exist_ok=True)
    work_dir = Path(tempfile.mkdtemp(prefix=".compress_pdf.", dir=output_real.parent))
    STATE.work_dir = work_dir

    try:
        return _run_pipeline_body(cfg, input_real, output_real, work_dir, ui_enabled)
    finally:
        shutil.rmtree(work_dir, ignore_errors=True)
        STATE.work_dir = None


def _run_pipeline_body(
    cfg: Config, input_real: Path, output_real: Path, work_dir: Path, ui_enabled: bool
) -> PipelineResult:
    verbose = cfg.verbose

    if pikepdf_check_encrypted(input_real):
        raise PdfCompressError(
            "Encrypted PDFs are not supported; decrypt the input first."
        )

    original_pages = page_count(input_real)

    if shutil.which("pdfsig"):
        sig = subprocess.run(
            ["pdfsig", str(input_real)], capture_output=True, text=True, check=False
        )
        if "Signature #" in sig.stdout:
            console.print(
                "[yellow]Warning:[/yellow] The input contains a digital signature; "
                "rewriting the PDF will invalidate it."
            )

    input_check_log = work_dir / "input-check.log"
    try:
        input_check_log.write_text("\n".join(pikepdf_check_syntax(input_real)))
        input_check_failed = False
    except pikepdf.PdfError as exc:
        input_check_log.write_text(str(exc))
        input_check_failed = True

    if input_check_failed:
        if cfg.mode == Mode.repair:
            console.print(
                "[yellow]Warning:[/yellow] Input validation failed; "
                "repair mode will attempt recovery."
            )
        else:
            show_stage_log(input_check_log)
            raise PdfCompressError("Input validation failed; retry with --mode repair.")

    pdfa_def: Path | None = None
    icc_profile: Path | None = None
    if cfg.pdfa_level != "none":
        icc_profile = find_icc_profile(cfg.icc_profile)
        pdfa_def = create_pdfa_definition(icc_profile, work_dir)

    current_file = input_real

    if cfg.flatten_annotations:
        flattened = work_dir / "flattened.pdf"
        run_pikepdf_stage(
            "Flattening annotations",
            lambda: pikepdf_flatten_annotations(current_file, flattened),
            work_dir,
            ui_enabled=ui_enabled,
            verbose=verbose,
        )
        current_file = flattened

    if cfg.mode == Mode.repair:
        repaired = work_dir / "repaired.pdf"
        run_pikepdf_stage(
            "Repairing PDF structure",
            lambda: pikepdf_repair(current_file, repaired),
            work_dir,
            ui_enabled=ui_enabled,
            verbose=verbose,
        )
        current_file = repaired
    elif cfg.mode == Mode.ps2pdf_recovery:
        recovered = work_dir / "recovered.pdf"
        ps2pdf_args = build_ps2pdf_args(in_file=current_file, out_file=recovered)
        run_ghostscript_lib(
            "Recovering through ps2pdf",
            ps2pdf_args,
            work_dir,
            ui_enabled=ui_enabled,
            verbose=verbose,
        )
        current_file = recovered

    if cfg.mode == Mode.lossless:
        candidate = work_dir / "candidate.pdf"
        run_pymupdf_stage(
            "Lossless PDF optimization",
            lambda: pymupdf_clean(
                current_file, candidate, drop_structure=cfg.drop_structure
            ),
            work_dir,
            ui_enabled=ui_enabled,
            verbose=verbose,
        )
    else:
        gs_file = work_dir / "ghostscript.pdf"
        gs_args = build_gs_args(
            in_file=current_file,
            out_file=gs_file,
            compat=cfg.compat,
            quality=cfg.quality.value,
            pdfa_level=cfg.pdfa_level,
            convert_color=cfg.convert_color,
            icc_profile=icc_profile,
            pdfa_def=pdfa_def,
        )
        run_ghostscript_lib(
            "Ghostscript compression",
            gs_args,
            work_dir,
            ui_enabled=ui_enabled,
            verbose=verbose,
            total_pages=original_pages,
        )
        if cfg.pdfa_level == "none":
            candidate = work_dir / "candidate.pdf"
            run_pymupdf_stage(
                "Lossless PDF cleanup",
                lambda: pymupdf_clean(
                    gs_file, candidate, drop_structure=cfg.drop_structure
                ),
                work_dir,
                ui_enabled=ui_enabled,
                verbose=verbose,
            )
        else:
            candidate = gs_file

    if cfg.linearize:
        linearized = work_dir / "linearized.pdf"
        run_pikepdf_stage(
            "Linearizing final PDF",
            lambda: pikepdf_linearize(candidate, linearized),
            work_dir,
            ui_enabled=ui_enabled,
            verbose=verbose,
        )
        candidate = linearized

    run_pikepdf_stage(
        "Validating PDF structure",
        lambda: pikepdf_check_syntax(candidate),
        work_dir,
        ui_enabled=ui_enabled,
        verbose=verbose,
    )

    new_pages = page_count(candidate)
    if new_pages != original_pages:
        raise PdfCompressError(
            f"Page count changed from {original_pages} to {new_pages}; "
            "output was not installed."
        )

    if cfg.pdfa_level != "none":
        validate_pdfa(cfg.pdfa_level, candidate, work_dir, ui_enabled=ui_enabled)

    original_bytes = file_bytes(input_real)
    new_bytes = file_bytes(candidate)

    if cfg.only_if_smaller and new_bytes >= original_bytes:
        console.print(
            "[yellow]Warning:[/yellow] Candidate is not smaller; "
            "destination was left unchanged."
        )
        return PipelineResult(
            input_file=input_real,
            output_file=output_real,
            original_bytes=original_bytes,
            new_bytes=new_bytes,
            pages=new_pages,
            pdfa_level=cfg.pdfa_level,
            installed=False,
        )

    shutil.move(str(candidate), str(output_real))

    return PipelineResult(
        input_file=input_real,
        output_file=output_real,
        original_bytes=original_bytes,
        new_bytes=new_bytes,
        pages=new_pages,
        pdfa_level=cfg.pdfa_level,
        installed=True,
    )


def validate_pdfa(
    level: str, candidate: Path, work_dir: Path, *, ui_enabled: bool
) -> None:
    name = f"Validating PDF/A-{level}b"
    report = work_dir / "verapdf-report.xml"
    log_file = work_dir / "verapdf.log"

    def _execute() -> tuple[int, str]:
        result = subprocess.run(
            ["verapdf", "--flavour", f"{level}b", "--format", "raw", str(candidate)],
            capture_output=True,
            text=True,
            check=False,
        )
        report.write_text(result.stdout)
        log_file.write_text(result.stderr)
        return result.returncode, result.stdout

    if ui_enabled:
        with console.status(f"[bold cyan]{name}...", spinner="dots"):
            status, output = _execute()
    else:
        err_console.print(f"{name}...")
        status, output = _execute()

    if status == 0 and 'isCompliant="true"' in output:
        if ui_enabled:
            console.print(f"[bold green]✓[/bold green] {name}")
        else:
            err_console.print(f"{name}: passed")
        return

    if ui_enabled:
        console.print(f"[bold red]✗[/bold red] {name}")
    show_stage_log(log_file)
    if report.exists() and report.stat().st_size:
        lines = report.read_text(errors="replace").splitlines()
        for line in lines[-30:]:
            err_console.print(line, style="dim", markup=False)
    raise PdfCompressError(f"The generated file is not compliant with PDF/A-{level}b.")
