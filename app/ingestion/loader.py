from dataclasses import dataclass, field
from pathlib import Path

from pypdf import PdfReader

SUPPORTED_EXTENSIONS = {".pdf", ".txt", ".md"}


@dataclass
class Document:
    text: str
    metadata: dict = field(default_factory=dict)


def load_document(path: Path) -> Document:
    suffix = path.suffix.lower()
    if suffix not in SUPPORTED_EXTENSIONS:
        raise ValueError(f"Unsupported file type: {suffix}")

    if suffix == ".pdf":
        reader = PdfReader(path)
        text = "\n".join(page.extract_text() or "" for page in reader.pages)
        pages = len(reader.pages)
    else:
        text = path.read_text(encoding="utf-8")
        pages = 1

    return Document(text=text, metadata={"source": path.name, "type": suffix[1:], "pages": pages})
