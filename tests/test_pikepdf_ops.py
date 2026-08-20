from __future__ import annotations

from pathlib import Path

import pikepdf
import pytest

from pdf_compress.pikepdf_ops import (
    pikepdf_check_encrypted,
    pikepdf_check_syntax,
    pikepdf_flatten_annotations,
    pikepdf_linearize,
    pikepdf_repair,
)
from pdf_compress.util import page_count


def test_check_encrypted_false_for_plain_pdf(sample_pdf: Path) -> None:
    assert pikepdf_check_encrypted(sample_pdf) is False


def test_check_encrypted_true_for_encrypted_pdf(encrypted_pdf: Path) -> None:
    assert pikepdf_check_encrypted(encrypted_pdf) is True


def test_check_syntax_clean_pdf_has_no_errors(sample_pdf: Path) -> None:
    warnings = pikepdf_check_syntax(sample_pdf)
    assert warnings == []


def test_check_syntax_raises_on_unparsable_garbage(garbage_pdf: Path) -> None:
    with pytest.raises(pikepdf.PdfError):
        pikepdf_check_syntax(garbage_pdf)


def test_check_syntax_reports_warnings_for_recoverable_damage(
    corrupted_pdf: Path,
) -> None:
    warnings = pikepdf_check_syntax(corrupted_pdf)
    assert any("damaged" in w or "reconstruct" in w for w in warnings)


def test_repair_recovers_page_content(corrupted_pdf: Path, tmp_path: Path) -> None:
    dst = tmp_path / "repaired.pdf"
    pikepdf_repair(corrupted_pdf, dst)
    assert dst.is_file()
    with pikepdf.open(dst) as pdf:
        assert len(pdf.pages) == 3
    # The repaired file gets a fresh, valid xref/trailer that pdfinfo can
    # read, even though the original corrupted file could not be.
    assert page_count(dst) == 3


def test_flatten_annotations_preserves_page_count(
    sample_pdf: Path, tmp_path: Path
) -> None:
    dst = tmp_path / "flattened.pdf"
    pikepdf_flatten_annotations(sample_pdf, dst)
    with pikepdf.open(sample_pdf) as src, pikepdf.open(dst) as out:
        assert len(out.pages) == len(src.pages)


def test_linearize_produces_valid_pdf(sample_pdf: Path, tmp_path: Path) -> None:
    dst = tmp_path / "linear.pdf"
    pikepdf_linearize(sample_pdf, dst)
    assert dst.is_file()
    with pikepdf.open(dst) as pdf:
        assert len(pdf.pages) == 3
        assert pikepdf_check_syntax(dst) == []
