"""Console output shared by the pipeline and the CLI (spinners, summaries, logs)."""

from __future__ import annotations

from pathlib import Path

from rich.console import Console
from rich.filesize import decimal
from rich.panel import Panel
from rich.table import Table

from pdf_compress.models import Config, Mode

console = Console()
err_console = Console(stderr=True)


def show_stage_log(log_file: Path | None) -> None:
    if log_file and log_file.exists() and log_file.stat().st_size:
        err_console.print("\n[dim]Last diagnostic messages:[/dim]")
        lines = log_file.read_text(errors="replace").splitlines()
        for line in lines[-50:]:
            err_console.print(line, style="dim", markup=False)


def show_dry_run(cfg: Config, input_real: Path, output_real: Path) -> None:
    lines = []
    if cfg.flatten_annotations:
        lines.append("pikepdf: generate appearances and flatten annotations")
    if cfg.mode == Mode.repair:
        lines.append("pikepdf: repair and normalize input")
    elif cfg.mode == Mode.ps2pdf_recovery:
        lines.append("Ghostscript (library): ps2pdf-style recovery conversion")
    if cfg.mode == Mode.lossless:
        lines.append("PyMuPDF: lossless structural and stream compression")
    else:
        lines.append(f"Ghostscript (library): {cfg.quality.value} compression")
        if cfg.pdfa_level == "none":
            lines.append("PyMuPDF: lossless cleanup")
        else:
            lines.append(
                "Ghostscript (library): create PDF/A-"
                f"{cfg.pdfa_level}b with an RGB output intent"
            )
    if cfg.linearize:
        lines.append("pikepdf: linearize final candidate")
    lines.append("pikepdf: structural validation")
    lines.append("PyMuPDF: page-count validation")
    if cfg.pdfa_level != "none":
        lines.append(f"veraPDF: PDF/A-{cfg.pdfa_level}b validation")

    body = "\n".join(f"[cyan]{i}.[/cyan] {line}" for i, line in enumerate(lines, 1))
    console.print(
        Panel(
            f"[bold]Input:[/bold]  {input_real}\n"
            f"[bold]Output:[/bold] {output_real}\n"
            f"[bold]Mode:[/bold]   {cfg.mode.value}\n\n"
            f"[bold]Pipeline:[/bold]\n{body}",
            title="Dry run",
            border_style="cyan",
        )
    )


def print_summary(
    *,
    output_real: Path,
    original_bytes: int,
    new_bytes: int,
    pages: int,
    pdfa_level: str,
) -> None:
    if original_bytes > 0:
        percent = (original_bytes - new_bytes) / original_bytes * 100
    else:
        percent = 0.0

    if new_bytes < original_bytes:
        result = f"{percent:.2f}% smaller"
        result_style = "bold green"
    elif new_bytes > original_bytes:
        result = f"{-percent:.2f}% larger"
        result_style = "bold red"
    else:
        result = "no size change"
        result_style = "yellow"

    console.print(f"[bold green]✓ Output installed:[/bold green] {output_real}")

    table = Table(
        title="Compression summary", show_header=False, box=None, padding=(0, 2)
    )
    table.add_column(style="bold")
    table.add_column()
    table.add_row("Original", f"{decimal(original_bytes)} ({original_bytes:,} bytes)")
    table.add_row("Output", f"{decimal(new_bytes)} ({new_bytes:,} bytes)")
    table.add_row("Result", f"[{result_style}]{result}[/{result_style}]")
    table.add_row("Pages", str(pages))
    if pdfa_level != "none":
        table.add_row("Format", f"PDF/A-{pdfa_level}b")
    console.print(table)
