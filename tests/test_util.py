from __future__ import annotations

from pathlib import Path

import pytest

from pdf_compress.errors import PdfCompressError
from pdf_compress.util import (
    create_pdfa_definition,
    file_bytes,
    find_icc_profile,
    has_digital_signature,
    page_count,
    postscript_escape,
    stage_log_path,
)


def test_file_bytes(sample_pdf: Path) -> None:
    assert file_bytes(sample_pdf) == sample_pdf.stat().st_size


def test_page_count(sample_pdf: Path) -> None:
    assert page_count(sample_pdf) == 3


def test_page_count_single(single_page_pdf: Path) -> None:
    assert page_count(single_page_pdf) == 1


def test_has_digital_signature_false_for_plain_pdf(sample_pdf: Path) -> None:
    assert has_digital_signature(sample_pdf) is False


def test_has_digital_signature_true_for_signed_pdf(signed_pdf: Path) -> None:
    assert has_digital_signature(signed_pdf) is True


def test_postscript_escape() -> None:
    assert postscript_escape(r"C:\a(b)c") == r"C:\\a\(b\)c"


def test_find_icc_profile_explicit(tmp_path: Path) -> None:
    profile = tmp_path / "custom.icc"
    profile.write_bytes(b"not a real icc profile")
    assert find_icc_profile(str(profile)) == profile.resolve()


def test_find_icc_profile_explicit_missing(tmp_path: Path) -> None:
    with pytest.raises(PdfCompressError):
        find_icc_profile(str(tmp_path / "missing.icc"))


def test_find_icc_profile_default_discovery() -> None:
    # Ghostscript is installed in this environment; the default profile
    # should be discoverable without an explicit path.
    profile = find_icc_profile(None)
    assert profile.is_file()


def test_create_pdfa_definition(tmp_path: Path) -> None:
    icc = tmp_path / "profile.icc"
    icc.write_bytes(b"stub")
    definition = create_pdfa_definition(icc, tmp_path)
    content = definition.read_text()
    assert "OutputIntent_PDFA" in content
    assert str(icc) in content


def test_stage_log_path_sanitizes_name(tmp_path: Path) -> None:
    log = stage_log_path(tmp_path, "Ghostscript compression!")
    assert log.parent == tmp_path
    assert log.name == "Ghostscript_compression_.log"
