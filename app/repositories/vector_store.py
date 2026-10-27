import threading
import uuid
from dataclasses import dataclass
from functools import lru_cache

import chromadb

from app.core.config import get_settings
from app.ingestion.chunker import Chunk

PAGE_SIZE = 20_000  # get() binds every id it returns: stay under SQLite's variable limit
# Chroma's client registry is not thread-safe, and requests run on a thread pool: the
# web app's first two requests (status and library) must not open the database at once.
_open_lock = threading.Lock()


@dataclass
class SearchResult:
    text: str
    metadata: dict
    score: float  # cosine similarity, higher is better


class VectorStore:
    def __init__(self, client: chromadb.ClientAPI, collection_name: str):
        self.collection = client.get_or_create_collection(
            collection_name, metadata={"hnsw:space": "cosine"}
        )
        self._catalog: tuple[int, dict[str, dict]] | None = None

    def add(
        self, chunks: list[Chunk], embeddings: list[list[float]], ids: list[str] | None = None
    ) -> None:
        self._catalog = None
        self.collection.upsert(
            ids=ids or [str(uuid.uuid4()) for _ in chunks],
            documents=[c.text for c in chunks],
            metadatas=[c.metadata for c in chunks],
            embeddings=embeddings,
        )

    def search(
        self, embedding: list[float], top_k: int = 5, where: dict | None = None
    ) -> list[SearchResult]:
        res = self.collection.query(query_embeddings=[embedding], n_results=top_k, where=where)
        return [
            SearchResult(text=doc, metadata=meta, score=1 - dist)
            for doc, meta, dist in zip(
                res["documents"][0], res["metadatas"][0], res["distances"][0], strict=True
            )
        ]

    def has_source(self, source: str) -> bool:
        return bool(self.collection.get(where={"source": source}, limit=1)["ids"])

    def delete_source(self, source: str) -> None:
        self._catalog = None
        self.collection.delete(where={"source": source})

    def count(self) -> int:
        return self.collection.count()

    def sources(self) -> dict[str, dict]:
        """Every indexed file with its title, type and chunk count.

        Reading all metadata takes a second or more on a large index, so the result is
        kept until the index changes (here, or in another process such as a bulk ingest).
        """
        count = self.count()
        if self._catalog is None or self._catalog[0] != count:
            catalog: dict[str, dict] = {}
            for offset in range(0, count, PAGE_SIZE):
                page = self.collection.get(include=["metadatas"], limit=PAGE_SIZE, offset=offset)
                for meta in page["metadatas"]:
                    entry = catalog.setdefault(meta["source"], {"chunks": 0})
                    entry["chunks"] += 1
                    entry.setdefault("title", meta.get("title", meta["source"]))
                    entry.setdefault("type", meta.get("type", ""))
            self._catalog = (count, catalog)
        return self._catalog[1]


@lru_cache
def get_vector_store() -> VectorStore:
    settings = get_settings()
    # One collection per embedding model: vectors from different models can't be mixed,
    # and Chroma fixes a collection's dimension at the first insert.
    model = settings.embedding_model.split("/")[-1]
    with _open_lock:
        client = chromadb.PersistentClient(path=settings.chroma_path)
        return VectorStore(client, f"{settings.collection_name}-{model}"[:63])
