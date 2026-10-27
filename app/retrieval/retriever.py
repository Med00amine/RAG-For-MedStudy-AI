from collections.abc import Sequence

from app.embeddings.embedder import Embedder
from app.repositories.vector_store import SearchResult, VectorStore


def is_textbook(source: str, textbook_paths: Sequence[str]) -> bool:
    return any(p in source for p in textbook_paths)


class Retriever:
    """Top-k cosine retrieval, dropping results below a minimum similarity.

    Textbooks hold three times more text than the lecture slides, so without help they
    crowd out the course material students are examined on. Passages from
    `textbook_paths` get a small ranking penalty: they still answer what the courses
    don't cover, but the faculty's own slides come first.
    """

    def __init__(
        self,
        embedder: Embedder,
        store: VectorStore,
        top_k: int,
        min_score: float,
        textbook_paths: Sequence[str] = (),
        textbook_penalty: float = 0.0,
    ):
        self.embedder = embedder
        self.store = store
        self.top_k = top_k
        self.min_score = min_score
        self.textbook_paths = textbook_paths
        self.textbook_penalty = textbook_penalty

    def _rank(self, result: SearchResult) -> float:
        textbook = is_textbook(result.metadata["source"], self.textbook_paths)
        return result.score - (self.textbook_penalty if textbook else 0.0)

    def retrieve(self, query: str, source: str | None = None) -> list[SearchResult]:
        embedding = self.embedder.embed_query(query)
        where = {"source": source} if source else None
        # Over-fetch so course passages just below the best textbook ones can move up.
        candidates = self.store.search(embedding, top_k=self.top_k * 4, where=where)
        # The threshold applies to the real similarity, the penalty only to the ranking.
        relevant = [r for r in candidates if r.score >= self.min_score]
        return sorted(relevant, key=self._rank, reverse=True)[: self.top_k]
