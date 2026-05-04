from __future__ import annotations

from pathlib import Path


def load_text_file(path: str) -> str:
    return Path(path).read_text(encoding="utf-8")


def load_pdf(path: str) -> str:
    from pypdf import PdfReader

    reader = PdfReader(path)
    return "\n\n".join(page.extract_text() or "" for page in reader.pages)


def load_docx(path: str) -> str:
    from docx import Document

    doc = Document(path)
    return "\n\n".join(p.text for p in doc.paragraphs if p.text.strip())


def load_file(path: str) -> str:
    """Load content from a file based on its extension."""
    ext = Path(path).suffix.lower()
    if ext == ".pdf":
        return load_pdf(path)
    elif ext == ".docx":
        return load_docx(path)
    elif ext in (".txt", ".md"):
        return load_text_file(path)
    else:
        raise ValueError(f"Unsupported file type: {ext}")
