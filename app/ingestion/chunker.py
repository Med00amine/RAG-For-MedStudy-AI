from dataclasses import dataclass, field

SEPARATORS = ["\n\n", "\n", ". ", " "]


@dataclass
class Chunk:
    text: str
    metadata: dict = field(default_factory=dict)


def _split(text: str, size: int, separators: list[str]) -> list[str]:
    """Recursively split text on the coarsest separator that yields pieces <= size."""
    if len(text) <= size:
        return [text]
    if not separators:
        return [text[i : i + size] for i in range(0, len(text), size)]

    sep, rest = separators[0], separators[1:]
    pieces: list[str] = []
    for part in text.split(sep):
        pieces.extend(_split(part, size, rest) if len(part) > size else [part])
    return [p for p in pieces if p.strip()]


def chunk_text(text: str, chunk_size: int = 800, overlap: int = 100) -> list[str]:
    chunks: list[str] = []
    current = ""
    for piece in _split(text, chunk_size - overlap, SEPARATORS):
        if current and len(current) + len(piece) + 1 > chunk_size:
            chunks.append(current.strip())
            current = current[-overlap:] if overlap else ""
        current = f"{current} {piece}" if current else piece
    if current.strip():
        chunks.append(current.strip())
    return chunks


def chunk_document(
    text: str, metadata: dict, chunk_size: int = 800, overlap: int = 100
) -> list[Chunk]:
    return [
        Chunk(text=t, metadata={**metadata, "chunk_index": i})
        for i, t in enumerate(chunk_text(text, chunk_size, overlap))
    ]
