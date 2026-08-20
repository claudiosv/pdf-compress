from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

from pdf_compress import __version__
from pdf_compress.cli import app

runner = CliRunner()


def test_version() -> None:
    result = runner.invoke(app, ["--version"])
    assert result.exit_code == 0
    assert __version__ in result.output


def test_help() -> None:
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "Compress and optimize" in result.output


def test_dry_run(sample_pdf: Path) -> None:
    result = runner.invoke(app, [str(sample_pdf), "--dry-run"])
    assert result.exit_code == 0
    assert "Dry run" in result.output


def test_missing_input_file_exits_with_usage_error(tmp_path: Path) -> None:
    result = runner.invoke(app, [str(tmp_path / "missing.pdf")])
    assert result.exit_code == 2
    assert "was not found" in result.output


def test_same_input_output_exits_with_usage_error(sample_pdf: Path) -> None:
    result = runner.invoke(app, [str(sample_pdf), str(sample_pdf)])
    assert result.exit_code == 2


def test_invalid_compatibility_is_usage_error(sample_pdf: Path, tmp_path: Path) -> None:
    out = tmp_path / "out.pdf"
    result = runner.invoke(app, [str(sample_pdf), str(out), "--compatibility", "9.9"])
    assert result.exit_code == 2


def test_compress_produces_output_file(sample_pdf: Path, tmp_path: Path) -> None:
    out = tmp_path / "out.pdf"
    result = runner.invoke(app, [str(sample_pdf), str(out), "--no-ui", "--force"])
    assert result.exit_code == 0, result.output
    assert out.is_file()
    assert "Output installed" in result.output


def test_qpdf_legacy_before_maps_to_repair(corrupted_pdf: Path, tmp_path: Path) -> None:
    out = tmp_path / "out.pdf"
    result = runner.invoke(
        app, [str(corrupted_pdf), str(out), "--qpdf", "before", "--no-ui"]
    )
    assert result.exit_code == 0, result.output
    assert out.is_file()
