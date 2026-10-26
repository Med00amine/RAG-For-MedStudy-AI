from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "RAG Service"
    upload_dir: str = "data/raw"
    log_level: str = "INFO"
    log_json: bool = False
    embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2"
    chroma_path: str = "data/chroma"
    collection_name: str = "documents"
    top_k: int = 5
    min_score: float = 0.3
    llm_model: str = "claude-opus-5-5"
    llm_max_tokens: int = 16000


@lru_cache
def get_settings() -> Settings:
    return Settings()
