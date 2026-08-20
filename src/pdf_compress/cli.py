"""Typer CLI for pdf_compress."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Annotated

import typer

from pdf_compress import __version__
from pdf_compress.errors import PdfCompressError, PipelineError, UsageError
from pdf_compress.models import Config, Mode, QpdfLegacy, Quality
from pdf_compress.pipeline import (
    install_signal_handlers,
    resolve_config,
    run_pipeline,
    validate_pdfa_constraints,
)
from pdf_compress.reporting import (
    console,
    err_console,
    print_summary,
    show_dry_run,
    show_stage_log,
)

app = typer.Typer(
    add_completion=False,
    help="Compress and optimize PDF files.",
    context_settings={"help_option_names": ["-h", "--help"]},
)


def version_callback(value: bool) -> None:
    if value:
        console.print(f"compress_pdf {__version__}")
        raise typer.Exit()


@app.command()
def main(
    input_file: Annotated[Path, typer.Argument(help="PDF file to compress.")],
    output_file: Annotated[
        Path | None,
        typer.Argument(help="Destination path (default: <input>_compressed.pdf)."),
    ] = None,
    mode: Annotated[Mode, typer.Option(help="Processing mode.")] = Mode.compress,
    quality: Annotated[
        Quality, typer.Option(help="Ghostscript PDFSETTINGS preset.")
    ] = Quality.ebook,
    compatibility: Annotated[
        str, typer.Option("--compatibility", help="PDF compatibility level, 1.2-1.7.")
    ] = "1.7",
    pdfa: Annotated[
        str | None, typer.Option(help="Produce and validate PDF/A-1b, 2b, or 3b.")
    ] = None,
    icc_profile: Annotated[
        str | None, typer.Option(help="RGB ICC profile for PDF/A output.")
    ] = None,
    flatten_annotations: Annotated[
        bool, typer.Option(help="Permanently bake annotations/forms into page content.")
    ] = False,
    drop_structure: Annotated[
        bool, typer.Option(help="Remove the tagged-PDF structure tree.")
    ] = False,
    no_convert_color: Annotated[
        bool,
        typer.Option(
            "--no-convert-color/--convert-color",
            help="Preserve source color spaces in non-PDF/A modes.",
        ),
    ] = False,
    linearize: Annotated[
        bool, typer.Option(help="Optimize the final PDF for web delivery.")
    ] = False,
    only_if_smaller: Annotated[
        bool, typer.Option(help="Do not install a candidate that is not smaller.")
    ] = False,
    force: Annotated[
        bool, typer.Option(help="Replace an existing output without prompting.")
    ] = False,
    dry_run: Annotated[
        bool, typer.Option(help="Show the selected pipeline without running it.")
    ] = False,
    verbose: Annotated[
        bool, typer.Option(help="Stream underlying tool output; disables live UI.")
    ] = False,
    no_ui: Annotated[
        bool, typer.Option(help="Disable rich progress and spinners.")
    ] = False,
    no_color: Annotated[bool, typer.Option(help="Disable rich/ANSI styling.")] = False,
    qpdf_legacy: Annotated[
        QpdfLegacy | None,
        typer.Option("--qpdf", help="Legacy: maps to repair mode or --linearize."),
    ] = None,
    ps2pdf_legacy: Annotated[
        bool, typer.Option("--ps2pdf", help="Legacy: maps to --mode ps2pdf-recovery.")
    ] = False,
    preserve_annots: Annotated[
        bool,
        typer.Option(
            "--preserve-annots",
            help="Accepted as a no-op; preservation is now the default.",
        ),
    ] = False,
    version: Annotated[
        bool | None,
        typer.Option("--version", callback=version_callback, is_eager=True),
    ] = None,
) -> None:
    """Compress and optimize a PDF file."""
    del preserve_annots, version  # accepted for compatibility / handled via callback

    if no_color:
        console.no_color = True
        err_console.no_color = True

    mode_explicit = mode != Mode.compress

    try:
        if qpdf_legacy == QpdfLegacy.before:
            if mode_explicit and mode != Mode.repair:
                raise UsageError(f"--qpdf before conflicts with --mode {mode.value}.")
            mode = Mode.repair
        elif qpdf_legacy == QpdfLegacy.after:
            linearize = True

        if ps2pdf_legacy:
            if qpdf_legacy == QpdfLegacy.before:
                raise UsageError("--ps2pdf conflicts with --qpdf before.")
            if mode_explicit and mode != Mode.ps2pdf_recovery:
                raise UsageError(f"--ps2pdf conflicts with --mode {mode.value}.")
            mode = Mode.ps2pdf_recovery

        if not re.fullmatch(r"1\.[2-7]", compatibility):
            raise UsageError("Compatibility must be between 1.2 and 1.7.")

        pdfa_level = "none"
        if pdfa is not None:
            pdfa_level = pdfa[:-1] if pdfa.endswith("b") else pdfa
            if pdfa_level not in ("1", "2", "3"):
                raise UsageError("PDF/A level must be 1, 2, or 3.")

        cfg = Config(
            mode=mode,
            quality=quality,
            compat=compatibility,
            compat_explicit=compatibility != "1.7",
            pdfa_level=pdfa_level,
            icc_profile=icc_profile,
            flatten_annotations=flatten_annotations,
            drop_structure=drop_structure,
            convert_color=not no_convert_color,
            linearize=linearize,
            only_if_smaller=only_if_smaller,
            force=force,
            dry_run=dry_run,
            verbose=verbose,
            no_ui=no_ui,
            no_color=no_color,
            input_file=input_file,
            output_file=output_file,
        )

        ui_enabled = not (no_ui or no_color or verbose) and console.is_terminal

        install_signal_handlers()

        if dry_run:
            input_real, output_real = resolve_config(cfg)
            cfg.compat = validate_pdfa_constraints(cfg)
            show_dry_run(cfg, input_real, output_real)
            raise typer.Exit(code=0)

        result = run_pipeline(cfg, ui_enabled)
    except UsageError as exc:
        err_console.print(f"[bold red]Error:[/bold red] {exc.message}")
        err_console.print("Try '--help' for usage.")
        raise typer.Exit(code=2) from None
    except PipelineError as exc:
        show_stage_log(exc.log_file)
        err_console.print(f"[bold red]Error:[/bold red] {exc.message}")
        raise typer.Exit(code=1) from None
    except PdfCompressError as exc:
        err_console.print(f"[bold red]Error:[/bold red] {exc.message}")
        raise typer.Exit(code=1) from None

    assert result is not None
    if result.installed:
        print_summary(
            output_real=result.output_file,
            original_bytes=result.original_bytes,
            new_bytes=result.new_bytes,
            pages=result.pages,
            pdfa_level=result.pdfa_level,
        )


if __name__ == "__main__":
    app()
