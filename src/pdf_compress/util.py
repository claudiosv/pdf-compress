from __future__ import annotations

import glob
import re
import shutil
import subprocess
from pathlib import Path

from pdf_compress.errors import PdfCompressError


def require_command(name: str, hint: str) -> str:
    path = shutil.which(name)
    if path is None:
        raise PdfCompressError(f"Missing '{name}'. {hint}")
    return path


def file_bytes(path: Path) -> int:
    return path.stat().st_size


def page_count(path: Path) -> int:
    result = subprocess.run(
        ["pdfinfo", str(path)], capture_output=True, text=True, check=False
    )
    for line in result.stdout.splitlines():
        if line.startswith("Pages:"):
            return int(line.split(":", 1)[1].strip())
    raise PdfCompressError("Unable to determine the page count.")


def postscript_escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def find_icc_profile(explicit: str | None) -> Path:
    if explicit:
        profile = Path(explicit).resolve()
        if not profile.is_file():
            raise PdfCompressError(f"ICC profile '{profile}' is not readable.")
        return profile

    gs_path = Path(require_command("gs", "Install Ghostscript.")).resolve()
    gs_prefix = gs_path.parent.parent
    candidates = [
        str(gs_prefix / "share" / "ghostscript" / "iccprofiles" / "default_rgb.icc"),
        "/opt/homebrew/share/ghostscript/*/iccprofiles/default_rgb.icc",
        "/usr/local/share/ghostscript/*/iccprofiles/default_rgb.icc",
        "/usr/share/ghostscript/*/iccprofiles/default_rgb.icc",
        "/usr/share/color/icc/ghostscript/default_rgb.icc",
    ]
    for pattern in candidates:
        for match in sorted(glob.glob(pattern)):
            path = Path(match)
            if path.is_file():
                return path.resolve()
    raise PdfCompressError(
        "Could not locate Ghostscript's default RGB ICC profile; use --icc-profile."
    )


def create_pdfa_definition(icc_profile: Path, work_dir: Path) -> Path:
    escaped = postscript_escape(str(icc_profile))
    content = (
        "%!\n"
        f"/ICCProfile ({escaped}) def\n"
        "[/_objdef {icc_PDFA} /type /stream /OBJ pdfmark\n"
        "[{icc_PDFA} << /N 3 >> /PUT pdfmark\n"
        "[ {icc_PDFA} ICCProfile (r) file /PUT pdfmark\n"
        "[/_objdef {OutputIntent_PDFA} /type /dict /OBJ pdfmark\n"
        "[{OutputIntent_PDFA} << /Type /OutputIntent /S /GTS_PDFA1 "
        "/DestOutputProfile {icc_PDFA} /OutputConditionIdentifier (sRGB) >> "
        "/PUT pdfmark\n"
        "[{Catalog} << /OutputIntents [{OutputIntent_PDFA}] >> /PUT pdfmark\n"
    )
    definition_path = work_dir / "PDFA_def.ps"
    definition_path.write_text(content)
    return definition_path


def stage_log_path(work_dir: Path, name: str) -> Path:
    safe_name = re.sub(r"[^A-Za-z0-9]", "_", name)
    return work_dir / f"{safe_name}.log"
