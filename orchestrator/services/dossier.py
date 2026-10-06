"""
Plain-text extraction for merchant dossier uploads (TXT, MD, JSON, PDF, DOCX).
"""

from __future__ import annotations

import csv
import io
import logging
import re
import zipfile
from xml.etree import ElementTree

TEXT_EXTENSIONS = {".txt", ".md", ".json", ".csv"}
SUPPORTED_EXTENSIONS = TEXT_EXTENSIONS | {".pdf", ".docx", ".xlsx", ".xls"}

logger = logging.getLogger(__name__)

# A .docx/.xlsx is a zip: cap the decompressed document so a small upload cannot expand to gigabytes.
MAX_DOCX_XML_BYTES = 50 * 1024 * 1024

_WORD_NS = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"


class DossierFormatError(Exception):
    """Raised when a dossier file type is unsupported or its content cannot be read."""


def _extension(filename: str) -> str:
    dot = filename.rfind(".")
    return filename[dot:].lower() if dot != -1 else ""


def _pdf_text(content: bytes) -> str:
    try:
        from pypdf import PdfReader
    except ImportError as exc:
        raise DossierFormatError("PDF dossiers need the 'pypdf' package installed on the server.") from exc
    try:
        reader = PdfReader(io.BytesIO(content))
        return "\n".join(page.extract_text() or "" for page in reader.pages)
    except Exception as exc:
        logger.warning("PDF dossier parse failed: %s", exc)
        raise DossierFormatError("Could not read the PDF file.") from exc


def _docx_text(content: bytes) -> str:
    try:
        with zipfile.ZipFile(io.BytesIO(content)) as archive:
            if archive.getinfo("word/document.xml").file_size > MAX_DOCX_XML_BYTES:
                raise DossierFormatError("The DOCX file is too large once decompressed.")
            root = ElementTree.fromstring(archive.read("word/document.xml"))
    except (zipfile.BadZipFile, KeyError, ElementTree.ParseError) as exc:
        logger.warning("DOCX dossier parse failed: %s", exc)
        raise DossierFormatError("Could not read the DOCX file.") from exc
    paragraphs = (
        "".join(node.text or "" for node in para.iter(f"{_WORD_NS}t"))
        for para in root.iter(f"{_WORD_NS}p")
    )
    return "\n".join(p for p in paragraphs if p)


def _excel_text(content: bytes) -> str:
    try:
        import openpyxl

        wb = openpyxl.load_workbook(io.BytesIO(content), data_only=True)
        lines: list[str] = []
        for sheet in wb.worksheets:
            lines.append(f"## Sheet: {sheet.title}")
            for row in sheet.iter_rows(values_only=True):
                vals = [str(c).strip() for c in row if c is not None and str(c).strip()]
                if vals:
                    lines.append(" | ".join(vals))
        return "\n".join(lines)
    except ImportError as exc:
        raise DossierFormatError("Excel spreadsheets need 'openpyxl' installed on the server.") from exc
    except Exception as exc:
        logger.warning("Excel spreadsheet parse failed: %s", exc)
        raise DossierFormatError("Could not read the Excel spreadsheet.") from exc


def _csv_text(content: bytes) -> str:
    try:
        text = content.decode("utf-8", errors="replace")
        reader = csv.reader(io.StringIO(text))
        rows = [" | ".join(c.strip() for c in r if c.strip()) for r in reader]
        return "\n".join(r for r in rows if r)
    except Exception as exc:
        logger.warning("CSV dossier parse failed: %s", exc)
        raise DossierFormatError("Could not read the CSV file.") from exc


def combine_documents(files: list[tuple[str, bytes]]) -> tuple[str, list[tuple[str, int]]]:
    """Extracts every file and joins them under '### <filename>' headers; returns (text, [(name, chars)])."""
    parts: list[str] = []
    info: list[tuple[str, int]] = []
    for name, content in files:
        try:
            text = extract_dossier_text(name, content)
        except DossierFormatError as exc:
            raise DossierFormatError(f"{name}: {exc}") from exc
        parts.append(f"### {name}\n{text}")
        info.append((name, len(text)))
    return "\n\n".join(parts), info


def extract_dossier_text(filename: str, content: bytes) -> str:
    ext = _extension(filename)
    if ext not in SUPPORTED_EXTENSIONS:
        raise DossierFormatError(
            f"Unsupported dossier type '{ext or filename}'. Allowed: {', '.join(sorted(SUPPORTED_EXTENSIONS))}"
        )

    if ext == ".pdf":
        text = _pdf_text(content)
    elif ext == ".docx":
        text = _docx_text(content)
    elif ext in {".xlsx", ".xls"}:
        text = _excel_text(content)
    elif ext == ".csv":
        text = _csv_text(content)
    else:
        text = content.decode("utf-8", errors="replace")

    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    if not text:
        raise DossierFormatError("The dossier contains no extractable text.")
    return text
