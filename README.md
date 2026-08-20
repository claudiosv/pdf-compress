# pdf-compress

Compress and optimize PDF files using Ghostscript, pikepdf, and PyMuPDF, with an
optional PDF/A conversion path validated by veraPDF.

## Install

```sh
uv sync
```

## CLI usage

```sh
uv run pdf-compress input.pdf
uv run pdf-compress input.pdf output.pdf --quality printer
uv run pdf-compress input.pdf --pdfa 2b
uv run pdf-compress --help
```

## Library usage

```python
from pdf_compress import compress, Mode, Quality

result = compress("input.pdf", mode=Mode.compress, quality=Quality.ebook)
print(result.output_file, result.original_bytes, result.new_bytes)
```

## Requirements

External tools: `gs` (Ghostscript), `pdfinfo` (Poppler), and `verapdf` (only needed
for `--pdfa` output).

## Development

```sh
uv sync
uv run pytest
uv run ruff check
```
