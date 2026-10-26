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

    def embed(self, texts: list[str]) -> list[list[float]]:
        start = time.perf_counter()
        vectors = self.model.encode(texts, normalize_embeddings=True)
        logger.info("Embedded %d texts in %.2fs", len(texts), time.perf_counter() - start)
        return vectors.tolist()


@lru_cache
def get_embedder() -> Embedder:
    # Loading the model is slow, so we keep a single instance per process.
    return Embedder(get_settings().embedding_model)
