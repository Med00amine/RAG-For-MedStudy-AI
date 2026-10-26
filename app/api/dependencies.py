from functools import lru_cache

from app.core.config import get_settings
from app.embeddings.embedder import get_embedder
from app.generation.llm import ClaudeLLM
from app.repositories.vector_store import get_vector_store
from app.retrieval.retriever import Retriever
from app.services.ingestion_service import IngestionService
from app.services.rag_service import RagService


def get_ingestion_service() -> IngestionService:
    return IngestionService(get_embedder(), get_vector_store())


@lru_cache
def get_rag_service() -> RagService:
    s = get_settings()
    retriever = Retriever(get_embedder(), get_vector_store(), s.top_k, s.min_score)
    return RagService(retriever, ClaudeLLM(s.llm_model, s.llm_max_tokens))
