"""Exception types shared by the library and the CLI.

Core modules raise these directly so the package works standalone as a
library; the CLI is the only place that catches them and turns them into
console output and process exit codes.
"""

from __future__ import annotations

from pathlib import Path


class PdfCompressError(Exception):
    """Base class for all errors raised by pdf_compress."""

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class UsageError(PdfCompressError):
    """Raised for invalid arguments or configuration."""


class PipelineError(PdfCompressError):
    """Raised when a pipeline stage fails; carries the path to its diagnostic log."""

    def __init__(self, message: str, log_file: Path | None = None) -> None:
        super().__init__(message)
        self.log_file = log_file
