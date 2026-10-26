import logging
from pathlib import Path

from app.embeddings.embedder import Embedder
from app.ingestion.chunker import chunk_document
from app.ingestion.cleaner import clean_text
from app.ingestion.loader import load_document
from app.repositories.vector_store import VectorStore

logger = logging.getLogger(__name__)


class IngestionService:
    def __init__(self, embedder: Embedder, store: VectorStore):
        self.embedder = embedder
        self.store = store

    def ingest(self, path: Path) -> int:
        doc = load_document(path)
        chunks = chunk_document(clean_text(doc.text), doc.metadata)
        if not chunks:
            return 0
        self.store.add(chunks, self.embedder.embed([c.text for c in chunks]))
        logger.info("Ingested %s: %d chunks", path.name, len(chunks))
        return len(chunks)
