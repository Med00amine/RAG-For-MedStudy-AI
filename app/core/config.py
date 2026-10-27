from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "RAG Service"
    upload_dir: str = "data/raw"
    log_level: str = "INFO"
    log_json: bool = False
    embedding_model: str = "intfloat/multilingual-e5-base"
    chroma_path: str = "data/chroma"
    ocr_cache_dir: str = "data/processed/ocr_cache"
    collection_name: str = "documents"
    top_k: int = 5
    min_score: float = 0.83  # calibrated with scripts/evaluate_retrieval.py
    llm_provider: Literal["ollama", "claude"] = "ollama"
    llm_model: str = "llama3.2"
    ollama_base_url: str = "http://localhost:11434"
    llm_max_tokens: int = 16000


@lru_cache
def get_settings() -> Settings:
    return Settings()
