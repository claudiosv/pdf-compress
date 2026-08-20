from __future__ import annotations

from pathlib import Path

import pikepdf

from pdf_compress.pymupdf_ops import pymupdf_clean
from pdf_compress.util import page_count


def test_clean_preserves_page_count(sample_pdf: Path, tmp_path: Path) -> None:
    dst = tmp_path / "cleaned.pdf"
    pymupdf_clean(sample_pdf, dst, drop_structure=False)
    assert page_count(dst) == page_count(sample_pdf)


def test_clean_produces_structurally_valid_pdf(
    sample_pdf: Path, tmp_path: Path
) -> None:
    dst = tmp_path / "cleaned.pdf"
    pymupdf_clean(sample_pdf, dst, drop_structure=False)
    with pikepdf.open(dst) as pdf:
        assert pdf.check_pdf_syntax() == []


def test_clean_drop_structure_removes_struct_tree_root(
    sample_pdf: Path, tmp_path: Path
) -> None:
    dst = tmp_path / "cleaned.pdf"
    pymupdf_clean(sample_pdf, dst, drop_structure=True)
    with pikepdf.open(dst) as pdf:
        assert "/StructTreeRoot" not in pdf.Root
