"""Turn an uploaded file into plain text for the extractor."""

import io

from pypdf import PdfReader
from pypdf.errors import PdfReadError

from app.digitize.errors import PermanentJobError

MAX_PAGES = 60
MAX_CHARS = 80_000  # keeps the LLM prompt (and cost) bounded


def extract_text(data: bytes, content_type: str, filename: str) -> str:
    if content_type == "application/pdf" or filename.lower().endswith(".pdf"):
        text = _pdf_text(data)
    else:
        text = data.decode("utf-8", errors="replace")

    text = text.strip()
    if not text:
        raise PermanentJobError(
            "No text found in this file. Scanned (image-only) PDFs need OCR, "
            "which is not supported yet."
        )
    return text[:MAX_CHARS]


def _pdf_text(data: bytes) -> str:
    try:
        reader = PdfReader(io.BytesIO(data))
        if reader.is_encrypted:
            raise PermanentJobError("This PDF is password-protected.")
        pages = reader.pages[:MAX_PAGES]
        return "\n".join(page.extract_text() or "" for page in pages)
    except PermanentJobError:
        raise
    except (PdfReadError, ValueError, KeyError) as exc:
        raise PermanentJobError(f"Could not read this PDF ({exc.__class__.__name__}).") from exc
