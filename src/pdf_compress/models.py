from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path


class Mode(str, Enum):  # noqa: UP042 -- typer needs a str-mixin Enum for CLI choices
    compress = "compress"
    lossless = "lossless"
    repair = "repair"
    ps2pdf_recovery = "ps2pdf-recovery"


class Quality(str, Enum):  # noqa: UP042
    screen = "screen"
    ebook = "ebook"
    printer = "printer"
    prepress = "prepress"
    default = "default"


class QpdfLegacy(str, Enum):  # noqa: UP042
    before = "before"
    after = "after"
    none = "none"


@dataclass
class Config:
    mode: Mode
    quality: Quality
    compat: str
    compat_explicit: bool
    pdfa_level: str
    icc_profile: str | None
    flatten_annotations: bool
    drop_structure: bool
    convert_color: bool
    linearize: bool
    only_if_smaller: bool
    force: bool
    dry_run: bool
    verbose: bool
    no_ui: bool
    no_color: bool
    input_file: Path
    output_file: Path | None


@dataclass
class PipelineResult:
    """Structured outcome of a pipeline run, for library callers."""

    input_file: Path
    output_file: Path
    original_bytes: int
    new_bytes: int
    pages: int
    pdfa_level: str
    installed: bool
