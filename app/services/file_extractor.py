"""Extract plain text from uploaded file attachments.

Supported: .txt, .md (UTF-8 decode), .docx (python-docx paragraph join).
PDF is left for Stage 4. Unsupported extensions raise ForgeError.
"""

from __future__ import annotations

import io
from pathlib import Path

from app.exceptions import ForgeError

_MAX_FILE_BYTES = 10 * 1024 * 1024  # 10 MB hard limit


def extract_text_from_file(content: bytes, filename: str) -> str:
    """Return plain text from a file's raw bytes.

    Raises:
        ForgeError: file is empty, too large, or has an unsupported extension.
    """
    if not content:
        raise ForgeError("File content is empty", code=400)
    if len(content) > _MAX_FILE_BYTES:
        raise ForgeError(f"File too large ({len(content)} bytes > 10 MB limit)", code=413)

    ext = Path(filename).suffix.lower()
    if ext in (".txt", ".md"):
        return content.decode("utf-8", errors="replace").strip()

    if ext == ".docx":
        try:
            from docx import Document  # type: ignore[import-untyped]

            doc = Document(io.BytesIO(content))
            return "\n".join(p.text for p in doc.paragraphs if p.text.strip())
        except ImportError as exc:
            raise ForgeError("python-docx is required to read .docx files") from exc

    raise ForgeError(
        f"Unsupported file type '{ext}'. Supported: .txt, .md, .docx",
        code=415,
    )
