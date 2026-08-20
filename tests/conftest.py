"""Real-PDF fixtures built with pymupdf/pikepdf — no mocking of PDF tooling."""

from __future__ import annotations

from pathlib import Path

import pikepdf
import pymupdf
import pytest


def _make_pdf(path: Path, *, pages: int = 3, with_image: bool = True) -> Path:
    doc = pymupdf.open()
    for i in range(pages):
        page = doc.new_page()
        page.insert_text(
            (72, 72), f"Hello world, page {i + 1} of {pages}.", fontsize=18
        )
        if with_image:
            pixmap = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, 64, 64))
            pixmap.set_rect(pixmap.irect, (i * 40 % 255, 100, 200))
            page.insert_image(pymupdf.Rect(72, 120, 200, 248), pixmap=pixmap)
    doc.save(path)
    doc.close()
    return path


@pytest.fixture
def sample_pdf(tmp_path: Path) -> Path:
    """A real, valid multi-page PDF with text and an embedded image."""
    return _make_pdf(tmp_path / "sample.pdf", pages=3)


@pytest.fixture
def single_page_pdf(tmp_path: Path) -> Path:
    return _make_pdf(tmp_path / "single.pdf", pages=1, with_image=False)


@pytest.fixture
def corrupted_pdf(tmp_path: Path, sample_pdf: Path) -> Path:
    """A PDF with a bogus ``startxref`` offset — a common real-world form of
    damage. The trailer/Root are otherwise intact, so pikepdf and pymupdf
    both transparently reconstruct the cross-reference table."""
    data = sample_pdf.read_bytes()
    offset = data.rindex(b"startxref\n") + len(b"startxref\n")
    end = data.index(b"\n", offset)
    path = tmp_path / "corrupted.pdf"
    path.write_bytes(data[:offset] + b"999999999" + data[end:])
    return path


@pytest.fixture
def garbage_pdf(tmp_path: Path) -> Path:
    """Bytes that aren't a PDF at all — neither pikepdf nor pymupdf can
    recover this."""
    path = tmp_path / "garbage.pdf"
    path.write_bytes(b"not a pdf at all, just garbage text 1234567890")
    return path


@pytest.fixture
def encrypted_pdf(tmp_path: Path, sample_pdf: Path) -> Path:
    path = tmp_path / "encrypted.pdf"
    with pikepdf.open(sample_pdf) as pdf:
        pdf.save(path, encryption=pikepdf.Encryption(owner="owner", user="secret"))
    return path


@pytest.fixture
def signed_pdf(tmp_path: Path, sample_pdf: Path) -> Path:
    """A PDF whose AcroForm declares signature fields (/SigFlags with the
    SignaturesExist bit set) — enough to trip the "will invalidate a
    signature" warning without needing a real cryptographic signature."""
    path = tmp_path / "signed.pdf"
    with pikepdf.open(sample_pdf) as pdf:
        acroform = pdf.make_indirect(
            pikepdf.Dictionary(Fields=pikepdf.Array([]), SigFlags=3)
        )
        pdf.Root.AcroForm = acroform
        pdf.save(path)
    return path
