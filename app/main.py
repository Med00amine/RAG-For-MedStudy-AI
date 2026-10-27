from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse

from app.api.errors import register_error_handlers
from app.api.middleware import register_request_logging
from app.api.routes import router
from app.core.config import get_settings
from app.core.logging import setup_logging
from app.repositories.vector_store import get_vector_store

STATIC_DIR = Path(__file__).parent / "static"

settings = get_settings()
setup_logging(settings.log_level, settings.log_json)

app = FastAPI(
    title=settings.app_name,
    description="Study assistant for medical students, answering from their course material.",
    version="0.1.0",
)
register_error_handlers(app)
register_request_logging(app)
app.include_router(router)


@app.get("/", include_in_schema=False)
def chat_page() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/health/ready")
def ready() -> dict[str, str | int]:
    """Readiness probe: verifies the vector store is reachable."""
    return {"status": "ready", "chunks": get_vector_store().count()}
