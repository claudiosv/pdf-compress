from __future__ import annotations

from pathlib import Path

import pytest

from pdf_compress import compress
from pdf_compress.errors import PdfCompressError, UsageError
from pdf_compress.models import Config, Mode, Quality
from pdf_compress.pipeline import run_pipeline
from pdf_compress.util import page_count


def _base_config(input_file: Path, output_file: Path, **overrides) -> Config:
    fields = dict(
        mode=Mode.compress,
        quality=Quality.ebook,
        compat="1.7",
        compat_explicit=False,
        pdfa_level="none",
        icc_profile=None,
        flatten_annotations=False,
        drop_structure=False,
        convert_color=True,
        linearize=False,
        only_if_smaller=False,
        force=True,
        dry_run=False,
        verbose=False,
        no_ui=True,
        no_color=True,
        input_file=input_file,
        output_file=output_file,
    )
    fields.update(overrides)
    return Config(**fields)


def test_compress_mode_end_to_end(sample_pdf: Path, tmp_path: Path) -> None:
    out = tmp_path / "out.pdf"
    result = run_pipeline(_base_config(sample_pdf, out))
    assert result is not None
    assert result.installed
    assert out.is_file()
    assert result.pages == page_count(sample_pdf)
    assert result.output_file == out.resolve()


def test_lossless_mode_end_to_end(sample_pdf: Path, tmp_path: Path) -> None:
    out = tmp_path / "out.pdf"
    result = run_pipeline(_base_config(sample_pdf, out, mode=Mode.lossless))
    assert result is not None
    assert result.installed
    assert page_count(out) == page_count(sample_pdf)


def test_repair_mode_recovers_corrupted_pdf(
    corrupted_pdf: Path, tmp_path: Path
) -> None:
    out = tmp_path / "out.pdf"
    result = run_pipeline(_base_config(corrupted_pdf, out, mode=Mode.repair))
    assert result is not None
    assert result.installed
    assert out.is_file()
    assert result.pages == 3


def test_unparsable_input_fails_with_clear_page_count_error(
    garbage_pdf: Path, tmp_path: Path
) -> None:
    # The pipeline needs a page count before any mode-specific stage runs,
    # so both compress and repair mode fail the same way for input that
    # isn't a PDF at all.
    out = tmp_path / "out.pdf"
    with pytest.raises(PdfCompressError, match="page count"):
        run_pipeline(_base_config(garbage_pdf, out, mode=Mode.repair))


def test_encrypted_pdf_is_rejected(encrypted_pdf: Path, tmp_path: Path) -> None:
    out = tmp_path / "out.pdf"
    with pytest.raises(PdfCompressError, match="Encrypted"):
        run_pipeline(_base_config(encrypted_pdf, out))


def test_signed_pdf_still_compresses_after_warning(
    signed_pdf: Path, tmp_path: Path
) -> None:
    # The signature warning is informational only; the pipeline still runs.
    out = tmp_path / "out.pdf"
    result = run_pipeline(_base_config(signed_pdf, out))
    assert result is not None
    assert result.installed


def test_pdfa_mode_produces_compliant_output(sample_pdf: Path, tmp_path: Path) -> None:
    out = tmp_path / "out.pdf"
    result = run_pipeline(_base_config(sample_pdf, out, pdfa_level="1", compat="1.4"))
    assert result is not None
    assert result.installed
    assert result.pdfa_level == "1"


def test_only_if_smaller_leaves_destination_unchanged_when_larger(
    single_page_pdf: Path, tmp_path: Path
) -> None:
    out = tmp_path / "out.pdf"
    result = run_pipeline(
        _base_config(
            single_page_pdf,
            out,
            quality=Quality.prepress,
            only_if_smaller=True,
        )
    )
    assert result is not None
    if not result.installed:
        assert not out.exists()


def test_same_input_and_output_is_usage_error(sample_pdf: Path) -> None:
    with pytest.raises(UsageError):
        run_pipeline(_base_config(sample_pdf, sample_pdf))


def test_missing_input_is_usage_error(tmp_path: Path) -> None:
    with pytest.raises(UsageError):
        run_pipeline(_base_config(tmp_path / "missing.pdf", tmp_path / "out.pdf"))


def test_pdfa_conflicts_with_lossless_mode(sample_pdf: Path, tmp_path: Path) -> None:
    with pytest.raises(UsageError):
        run_pipeline(
            _base_config(
                sample_pdf, tmp_path / "out.pdf", mode=Mode.lossless, pdfa_level="1"
            )
        )


def test_library_compress_function(sample_pdf: Path, tmp_path: Path) -> None:
    out = tmp_path / "out.pdf"
    result = compress(sample_pdf, out)
    assert result.installed
    assert result.output_file == out.resolve()
    assert result.pages == page_count(sample_pdf)
