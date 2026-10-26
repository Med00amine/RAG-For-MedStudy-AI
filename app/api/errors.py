import logging

import anthropic
import httpx
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(ValueError)
    async def value_error(_: Request, exc: ValueError) -> JSONResponse:
        return JSONResponse(status_code=400, content={"detail": str(exc)})

    @app.exception_handler(anthropic.APIError)
    @app.exception_handler(httpx.HTTPError)
    async def llm_error(_: Request, exc: Exception) -> JSONResponse:
        logger.error("LLM provider error: %s", exc)
        return JSONResponse(status_code=502, content={"detail": "LLM provider unavailable"})

    @app.exception_handler(Exception)
    async def unhandled(_: Request, exc: Exception) -> JSONResponse:
        logger.exception("Unhandled error")
        return JSONResponse(status_code=500, content={"detail": "Internal server error"})
