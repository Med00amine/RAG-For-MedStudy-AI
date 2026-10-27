import logging
from pathlib import Path

from app.embeddings.embedder import Embedder
from app.ingestion.chunker import Chunk, chunk_document
from app.ingestion.cleaner import clean_text
from app.ingestion.loader import load_document
from app.repositories.vector_store import VectorStore

logger = logging.getLogger(__name__)

MIN_CHUNK_CHARS = 20  # drop slide titles like "Plan" that carry no information


class IngestionService:
    def __init__(self, embedder: Embedder, store: VectorStore):
        self.embedder = embedder
        self.store = store

    def ingest(self, path: Path, source: str | None = None) -> int:
        """Load, chunk and index one file. Re-ingesting a source replaces its old chunks."""
        doc = load_document(path)
        metadata = {**doc.metadata, "source": source or path.name}

        chunks: list[Chunk] = []
        for page in doc.pages:
            page_meta = metadata if page.number is None else {**metadata, "page": page.number}
            chunks += chunk_document(clean_text(page.text), page_meta)
        chunks = [c for c in chunks if len(c.text) >= MIN_CHUNK_CHARS]
        for i, chunk in enumerate(chunks):
            chunk.metadata["chunk_index"] = i

        self.store.delete_source(metadata["source"])
        if chunks:
            # Prefix the lecture title so a bare slide like "Traitement: ..." is still findable.
            texts = [f"{metadata['title']}\n{c.text}" for c in chunks]
            ids = [f"{metadata['source']}#{c.metadata['chunk_index']}" for c in chunks]
            self.store.add(chunks, self.embedder.embed(texts), ids=ids)
        logger.info("Ingested %s: %d chunks", metadata["source"], len(chunks))
        return len(chunks)
