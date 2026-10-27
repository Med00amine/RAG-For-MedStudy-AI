import logging
import time
from functools import lru_cache

from sentence_transformers import SentenceTransformer

from app.core.config import get_settings

logger = logging.getLogger(__name__)


class Embedder:
    """Turns text into dense vectors. Vectors are normalized so dot product == cosine."""

    def __init__(self, model_name: str):
        self.model = SentenceTransformer(model_name)
        # E5 models are trained with these prefixes and retrieve worse without them.
        is_e5 = "e5" in model_name.lower()
        self.query_prefix, self.passage_prefix = ("query: ", "passage: ") if is_e5 else ("", "")

    def _encode(self, texts: list[str]) -> list[list[float]]:
        start = time.perf_counter()
        vectors = self.model.encode(texts, normalize_embeddings=True, batch_size=32)
        logger.info("Embedded %d texts in %.2fs", len(texts), time.perf_counter() - start)
        return vectors.tolist()

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return self._encode([self.passage_prefix + t for t in texts])

    def embed_query(self, text: str) -> list[float]:
        return self._encode([self.query_prefix + text])[0]


@lru_cache
def get_embedder() -> Embedder:
    # Loading the model is slow, so we keep a single instance per process.
    return Embedder(get_settings().embedding_model)
