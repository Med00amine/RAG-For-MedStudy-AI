from fastapi import FastAPI

from app.api.errors import register_error_handlers
from app.api.routes import router
from app.core.config import get_settings
from app.core.logging import setup_logging

settings = get_settings()
setup_logging(settings.log_level)

app = FastAPI(
    title=settings.app_name,
    description="Upload documents and ask questions answered from their content.",
    version="0.1.0",
)
register_error_handlers(app)
app.include_router(router)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
