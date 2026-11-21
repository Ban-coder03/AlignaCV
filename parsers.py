"""Extracción y normalización de texto desde archivos subidos (.pdf y .docx).

Seguridad:
- Se valida la extensión Y la firma real del archivo (magic bytes).
- Los .docx (zip) se inspeccionan antes de abrirlos para evitar "zip bombs".
- Se limitan las páginas de PDF procesadas.
- Nada se escribe en disco: todo se procesa en memoria.
"""

import io
import logging
import re
import unicodedata
import zipfile
from dataclasses import dataclass, field
from pathlib import PurePath

from errors import FileParseError, UnsupportedFileTypeError

logger = logging.getLogger("cv_analyzer.parsers")

MAX_PDF_PAGES = 20
MAX_DOCX_UNCOMPRESSED_BYTES = 50 * 1024 * 1024   # descomprimido, para frenar zip bombs
MIN_USEFUL_CHARS = 50                              # menos que esto → probablemente sin texto (escaneado)

PDF_MAGIC = b"%PDF-"
ZIP_MAGIC = b"PK\x03\x04"


@dataclass
class ExtractedDocument:
    filename: str
    file_type: str                  # "pdf" | "docx"
    text: str
    pages: int | None = None
    warnings: list[str] = field(default_factory=list)


# ============================================================================================
# Limpieza y normalización
# ============================================================================================
_BULLETS = "•●▪■◦○▫‣⁃∙·"
_BULLET_RE = re.compile(rf"^[ \t]*[{re.escape(_BULLETS)}][ \t]*", re.MULTILINE)
_HYPHEN_BREAK_RE = re.compile(r"(?<=[a-záéíóúüñ])-\n(?=[a-záéíóúüñ])")   # "desarro-\nllo" → "desarrollo"
_CONTROL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


def normalize_text(text: str) -> str:
    """Deja el texto limpio y predecible para el análisis.

    - Unicode NFKC (ligaduras "ﬁ"→"fi", espacios raros, etc.)
    - Elimina caracteres de control y bytes nulos
    - Unifica saltos de línea, viñetas ("•" → "- ") y espacios
    - Une palabras cortadas por guion al final de línea (típico de PDFs)
    - Colapsa líneas en blanco repetidas
    """
    if not text:
        return ""
    text = unicodedata.normalize("NFKC", text)
    text = text.replace("\r\n", "\n").replace("\r", "\n").replace("­", "")  # guion blando
    text = _CONTROL_RE.sub("", text)
    text = text.replace(" ", " ").replace("​", "").replace("﻿", "")
    text = _HYPHEN_BREAK_RE.sub("", text)
    text = _BULLET_RE.sub("- ", text)
    lines = [re.sub(r"[ \t]+", " ", line).strip() for line in text.split("\n")]
    text = "\n".join(lines)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


# ============================================================================================
# PDF
# ============================================================================================
def extract_text_from_pdf(data: bytes) -> tuple[str, int, list[str]]:
    """Devuelve (texto, páginas_leídas, avisos). Lanza FileParseError si no se puede leer."""
    try:
        from pypdf import PdfReader
        from pypdf.errors import PdfReadError
    except ImportError as exc:  # pragma: no cover - depende del entorno
        raise FileParseError("Falta la dependencia 'pypdf' en el servidor.") from exc

    warnings: list[str] = []
    try:
        reader = PdfReader(io.BytesIO(data))
        if reader.is_encrypted:
            # Muchos PDFs "protegidos" solo tienen contraseña de propietario (clave de usuario vacía).
            if not reader.decrypt(""):
                raise FileParseError("El PDF está protegido con contraseña. Quita la contraseña y vuelve a subirlo.")
        total_pages = len(reader.pages)
        pages_to_read = min(total_pages, MAX_PDF_PAGES)
        if total_pages > MAX_PDF_PAGES:
            warnings.append(f"El PDF tiene {total_pages} páginas; solo se leyeron las primeras {MAX_PDF_PAGES}.")
        chunks = []
        for index in range(pages_to_read):
            try:
                chunks.append(reader.pages[index].extract_text() or "")
            except Exception:  # una página corrupta no debe tumbar todo el documento
                logger.warning("No se pudo extraer texto de la página %d", index + 1)
                warnings.append(f"No se pudo leer la página {index + 1}.")
    except FileParseError:
        raise
    except PdfReadError as exc:
        raise FileParseError("El PDF está dañado o no es válido.") from exc
    except Exception as exc:
        logger.warning("Error inesperado leyendo PDF: %s", type(exc).__name__)
        raise FileParseError("No se pudo leer el PDF. Comprueba que no esté dañado.") from exc

    return "\n\n".join(chunks), pages_to_read, warnings


# ============================================================================================
# DOCX
# ============================================================================================
def _check_zip_is_safe(data: bytes) -> None:
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            total = sum(info.file_size for info in archive.infolist())
            if total > MAX_DOCX_UNCOMPRESSED_BYTES:
                raise FileParseError("El documento Word es demasiado grande una vez descomprimido.")
            if "word/document.xml" not in archive.namelist():
                raise FileParseError("El archivo no es un documento Word (.docx) válido.")
    except zipfile.BadZipFile as exc:
        raise FileParseError("El archivo .docx está dañado o no es válido.") from exc


def extract_text_from_docx(data: bytes) -> str:
    """Extrae párrafos Y tablas en orden de aparición (muchas plantillas de CV usan tablas)."""
    try:
        from docx import Document
        from docx.table import Table
        from docx.text.paragraph import Paragraph
    except ImportError as exc:  # pragma: no cover - depende del entorno
        raise FileParseError("Falta la dependencia 'python-docx' en el servidor.") from exc

    _check_zip_is_safe(data)
    try:
        document = Document(io.BytesIO(data))
        lines: list[str] = []
        for child in document.element.body.iterchildren():
            tag = child.tag.rsplit("}", 1)[-1]
            if tag == "p":
                lines.append(Paragraph(child, document).text)
            elif tag == "tbl":
                seen_cells: set[int] = set()
                for row in Table(child, document).rows:
                    cells: list[str] = []
                    for cell in row.cells:
                        if id(cell._tc) in seen_cells:   # celdas combinadas se repiten
                            continue
                        seen_cells.add(id(cell._tc))
                        cell_text = " ".join(p.text.strip() for p in cell.paragraphs if p.text.strip())
                        if cell_text:
                            cells.append(cell_text)
                    if cells:
                        lines.append(" | ".join(cells))
        return "\n".join(lines)
    except FileParseError:
        raise
    except Exception as exc:
        logger.warning("Error inesperado leyendo DOCX: %s", type(exc).__name__)
        raise FileParseError("No se pudo leer el documento Word. Comprueba que no esté dañado.") from exc


# ============================================================================================
# Punto de entrada
# ============================================================================================
def detect_file_type(filename: str, data: bytes) -> str:
    """Valida extensión + firma real. Devuelve 'pdf' o 'docx'."""
    ext = PurePath(filename or "").suffix.lower()
    if ext == ".doc":
        raise UnsupportedFileTypeError("El formato .doc antiguo no está soportado. Guarda el CV como .docx o .pdf.")
    if ext not in (".pdf", ".docx"):
        raise UnsupportedFileTypeError()
    if ext == ".pdf":
        if not data.lstrip()[:5] == PDF_MAGIC:
            raise UnsupportedFileTypeError("El archivo no parece ser un PDF válido.")
        return "pdf"
    if not data.startswith(ZIP_MAGIC):
        raise UnsupportedFileTypeError("El archivo no parece ser un documento Word (.docx) válido.")
    return "docx"


def extract_text(filename: str, data: bytes) -> ExtractedDocument:
    """Extrae y normaliza el texto de un CV subido como .pdf o .docx."""
    if not data:
        raise FileParseError("El archivo está vacío.")
    safe_name = PurePath(filename or "cv").name[:120]
    file_type = detect_file_type(safe_name, data)

    if file_type == "pdf":
        raw, pages, warnings = extract_text_from_pdf(data)
    else:
        raw, pages, warnings = extract_text_from_docx(data), None, []

    text = normalize_text(raw)
    if len(text) < MIN_USEFUL_CHARS:
        hint = " Parece un PDF escaneado (imagen): exporta el CV con texto seleccionable o pega el texto manualmente." if file_type == "pdf" else ""
        raise FileParseError(f"No se encontró texto suficiente en el archivo.{hint}")
    return ExtractedDocument(filename=safe_name, file_type=file_type, text=text, pages=pages, warnings=warnings)
