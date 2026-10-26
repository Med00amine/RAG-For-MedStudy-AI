from app.embeddings.embedder import Embedder
from app.repositories.vector_store import SearchResult, VectorStore


class Retriever:
    """Top-k cosine retrieval, dropping results below a minimum similarity."""

    def __init__(self, embedder: Embedder, store: VectorStore, top_k: int, min_score: float):
        self.embedder = embedder
        self.store = store
        self.top_k = top_k
        self.min_score = min_score

    def retrieve(self, query: str, source: str | None = None) -> list[SearchResult]:
        [embedding] = self.embedder.embed([query])
        where = {"source": source} if source else None
        results = self.store.search(embedding, top_k=self.top_k, where=where)
        return [r for r in results if r.score >= self.min_score]
