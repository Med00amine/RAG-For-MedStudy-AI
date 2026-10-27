import json
import logging
import secrets
from collections.abc import Iterator
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, UploadFile
from fastapi.responses import StreamingResponse

from app.api.dependencies import get_ingestion_service, get_rag_service
from app.core.config import get_settings
from app.generation.prompts import locate
from app.ingestion.loader import SUPPORTED_EXTENSIONS
from app.repositories.vector_store import SearchResult
from app.schemas.rag import IngestResponse, QueryRequest, QueryResponse, Source
from app.services.ingestion_service import IngestionService
from app.services.rag_service import RagService

logger = logging.getLogger(__name__)
router = APIRouter()

IngestionDep = Annotated[IngestionService, Depends(get_ingestion_service)]
RagDep = Annotated[RagService, Depends(get_rag_service)]


def to_source(result: SearchResult) -> Source:
    meta = result.metadata
    return Source(
        source=meta["source"],
        title=meta.get("title", meta["source"]),
        page=meta.get("page"),
        location=locate(result),
        chunk_index=meta["chunk_index"],
        score=round(result.score, 4),
        text=result.text,
    )


def require_admin(x_admin_token: Annotated[str, Header()] = "") -> None:
    """Only maintainers may add course material: it is what students will trust."""
    expected = get_settings().admin_token
    if not expected or not secrets.compare_digest(x_admin_token, expected):
        raise HTTPException(403, "Adding documents requires a valid X-Admin-Token header")


@router.post(
    "/documents",
    response_model=IngestResponse,
    status_code=201,
    dependencies=[Depends(require_admin)],
)
def upload_document(file: UploadFile, service: IngestionDep) -> IngestResponse:
    filename = Path(file.filename or "").name
    if Path(filename).suffix.lower() not in SUPPORTED_EXTENSIONS:
        raise HTTPException(415, f"Supported types: {', '.join(sorted(SUPPORTED_EXTENSIONS))}")

    upload_dir = Path(get_settings().upload_dir)
    upload_dir.mkdir(parents=True, exist_ok=True)
    path = upload_dir / filename
    path.write_bytes(file.file.read())

    return IngestResponse(filename=filename, chunks=service.ingest(path))


@router.post("/query", response_model=QueryResponse)
def query(req: QueryRequest, service: RagDep) -> QueryResponse:
    history = [m.model_dump() for m in req.history]
    result = service.ask(req.question, history, source=req.source)
    return QueryResponse(answer=result.answer, sources=[to_source(r) for r in result.sources])


@router.post("/chat")
def chat(req: QueryRequest, service: RagDep) -> StreamingResponse:
    """Stream the answer as NDJSON: a `sources` event, `token` events, then `done`."""
    history = [m.model_dump() for m in req.history]
    results = service.retrieve(req.question, history, source=req.source)

    def events() -> Iterator[str]:
        sources = [to_source(r).model_dump() for r in results]
        yield json.dumps({"type": "sources", "sources": sources}) + "\n"
        try:
            for token in service.stream_answer(req.question, results, history):
                yield json.dumps({"type": "token", "text": token}) + "\n"
        except Exception:  # headers are already sent: report the failure in the stream
            logger.exception("LLM failed while streaming")
            yield json.dumps({"type": "error", "message": "LLM provider unavailable"}) + "\n"
        yield json.dumps({"type": "done"}) + "\n"

    # Without this header Nginx buffers the stream and the answer arrives all at once.
    return StreamingResponse(
        events(), media_type="application/x-ndjson", headers={"X-Accel-Buffering": "no"}
    )
