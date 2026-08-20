"""Compress and optimize PDF files using Ghostscript, pikepdf, and PyMuPDF.

Library usage:

    from pdf_compress import compress, Mode, Quality

    result = compress("input.pdf", mode=Mode.compress, quality=Quality.ebook)
    print(result.output_file, result.new_bytes)
"""

from __future__ import annotations

from pathlib import Path

from pdf_compress.errors import PdfCompressError, PipelineError, UsageError
from pdf_compress.models import Config, Mode, PipelineResult, Quality
from pdf_compress.pipeline import run_pipeline

__version__ = "2.0.0"

__all__ = [
    "Config",
    "Mode",
    "PdfCompressError",
    "PipelineError",
    "PipelineResult",
    "Quality",
    "UsageError",
    "compress",
    "run_pipeline",
]


def compress(
    input_file: str | Path,
    output_file: str | Path | None = None,
    *,
    mode: Mode = Mode.compress,
    quality: Quality = Quality.ebook,
    compatibility: str = "1.7",
    pdfa_level: str = "none",
    icc_profile: str | None = None,
    flatten_annotations: bool = False,
    drop_structure: bool = False,
    convert_color: bool = True,
    linearize: bool = False,
    only_if_smaller: bool = False,
    force: bool = True,
) -> PipelineResult:
    """Compress a single PDF file and return a :class:`PipelineResult`.

    This is the library entry point: no console output, no dry-run mode, no
    interactive prompts. Raises :class:`PdfCompressError` (or one of its
    subclasses) on failure.
    """
    cfg = Config(
        mode=mode,
        quality=quality,
        compat=compatibility,
        compat_explicit=compatibility != "1.7",
        pdfa_level=pdfa_level,
        icc_profile=icc_profile,
        flatten_annotations=flatten_annotations,
        drop_structure=drop_structure,
        convert_color=convert_color,
        linearize=linearize,
        only_if_smaller=only_if_smaller,
        force=force,
        dry_run=False,
        verbose=False,
        no_ui=True,
        no_color=True,
        input_file=Path(input_file),
        output_file=Path(output_file) if output_file is not None else None,
    )
    result = run_pipeline(cfg, ui_enabled=False)
    assert result is not None
    return result
