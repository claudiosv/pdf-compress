from __future__ import annotations

from pathlib import Path

from pdf_compress.ghostscript import (
    build_gs_args,
    build_ps2pdf_args,
    ghostscript_module,
    run_ghostscript_lib,
)
from pdf_compress.util import page_count


def test_build_gs_args_basic() -> None:
    args = build_gs_args(
        in_file=Path("in.pdf"),
        out_file=Path("out.pdf"),
        compat="1.7",
        quality="ebook",
        pdfa_level="none",
        convert_color=True,
        icc_profile=None,
        pdfa_def=None,
    )
    assert "-sDEVICE=pdfwrite" in args
    assert "-dPDFSETTINGS=/ebook" in args
    assert "-sColorConversionStrategy=RGB" in args
    assert args[-2] == "-sOutputFile=out.pdf"
    assert args[-1] == "in.pdf"


def test_build_gs_args_pdfa_adds_output_intent(tmp_path: Path) -> None:
    icc = tmp_path / "profile.icc"
    pdfa_def = tmp_path / "PDFA_def.ps"
    args = build_gs_args(
        in_file=Path("in.pdf"),
        out_file=Path("out.pdf"),
        compat="1.4",
        quality="ebook",
        pdfa_level="1",
        convert_color=True,
        icc_profile=icc,
        pdfa_def=pdfa_def,
    )
    assert "-dPDFA=1" in args
    assert f"--permit-file-read={icc}" in args
    assert str(pdfa_def) in args
    assert args[-1] == "in.pdf"
    assert args[-2] == str(pdfa_def)


def test_build_ps2pdf_args() -> None:
    args = build_ps2pdf_args(in_file=Path("in.ps"), out_file=Path("out.pdf"))
    assert "-sOutputFile=out.pdf" in args
    assert args[-1] == "in.ps"


def test_ghostscript_module_loads() -> None:
    # Ghostscript is installed in this environment.
    module = ghostscript_module()
    assert hasattr(module, "Ghostscript")


def test_run_ghostscript_lib_compresses_real_pdf(
    sample_pdf: Path, tmp_path: Path
) -> None:
    out_file = tmp_path / "out.pdf"
    args = build_gs_args(
        in_file=sample_pdf,
        out_file=out_file,
        compat="1.7",
        quality="ebook",
        pdfa_level="none",
        convert_color=True,
        icc_profile=None,
        pdfa_def=None,
    )
    run_ghostscript_lib(
        "test compression", args, tmp_path, ui_enabled=False, verbose=False
    )
    assert out_file.is_file()
    assert page_count(out_file) == page_count(sample_pdf)
