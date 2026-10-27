import uuid
from dataclasses import dataclass
from functools import lru_cache

import chromadb

from app.core.config import get_settings
from app.ingestion.chunker import Chunk


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

    def add(
        self, chunks: list[Chunk], embeddings: list[list[float]], ids: list[str] | None = None
    ) -> None:
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
        self.collection.delete(where={"source": source})

    def count(self) -> int:
        return self.collection.count()


@lru_cache
def get_vector_store() -> VectorStore:
    settings = get_settings()
    client = chromadb.PersistentClient(path=settings.chroma_path)
    # One collection per embedding model: vectors from different models can't be mixed,
    # and Chroma fixes a collection's dimension at the first insert.
    model = settings.embedding_model.split("/")[-1]
    return VectorStore(client, f"{settings.collection_name}-{model}"[:63])
