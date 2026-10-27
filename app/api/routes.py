import json
import logging
import secrets
from collections.abc import Iterator
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, UploadFile
from fastapi.responses import FileResponse, StreamingResponse

from app.api.dependencies import get_ingestion_service, get_rag_service
from app.core.config import get_settings
from app.generation.prompts import locate
from app.ingestion.loader import SUPPORTED_EXTENSIONS
from app.repositories.vector_store import SearchResult, VectorStore, get_vector_store
from app.retrieval.retriever import is_textbook
from app.schemas.rag import (
    DocumentInfo,
    DocumentList,
    IngestResponse,
    QueryRequest,
    QueryResponse,
    Source,
)
from app.services.ingestion_service import IngestionService
from app.services.rag_service import RagService

logger = logging.getLogger(__name__)
router = APIRouter()

IngestionDep = Annotated[IngestionService, Depends(get_ingestion_service)]
RagDep = Annotated[RagService, Depends(get_rag_service)]
StoreDep = Annotated[VectorStore, Depends(get_vector_store)]

# Opened in the browser (a PDF at the cited page); slides and Word files are downloaded.
INLINE_TYPES = {".pdf", ".png", ".jpg", ".jpeg", ".txt"}


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
    """Only maintainers may change the course material: it is what students will trust."""
    expected = get_settings().admin_token
    if not expected or not secrets.compare_digest(x_admin_token, expected):
        raise HTTPException(403, "Changing documents requires a valid X-Admin-Token header")


def source_file(source: str) -> Path | None:
    """The original file of an indexed source, only if it lies inside a library folder."""
    settings = get_settings()
    for folder in (settings.upload_dir, *settings.source_dirs):
        root = Path(folder).resolve()
        path = (root / source).resolve()
        if path.is_relative_to(root) and path.is_file():
            return path
    return None


def can_open(source: str) -> bool:
    # Textbooks are quoted in answers, never handed out whole.
    textbook = is_textbook(source, get_settings().textbook_paths)
    return not textbook and source_file(source) is not None


@router.get("/documents", response_model=DocumentList)
def list_documents(store: StoreDep) -> DocumentList:
    settings = get_settings()
    documents = [
        DocumentInfo(
            source=source,
            **info,
            textbook=is_textbook(source, settings.textbook_paths),
            openable=can_open(source),
        )
        for source, info in sorted(store.sources().items())
    ]
    return DocumentList(
        documents=documents,
        uploads_enabled=bool(settings.admin_token),
        upload_types=sorted(SUPPORTED_EXTENSIONS),
    )


@router.get("/documents/file")
def document_file(source: str, store: StoreDep) -> FileResponse:
    """The original course file, so students can check the cited slide or page."""
    if source not in store.sources() or not can_open(source):
        raise HTTPException(404, "No openable document with this source")
    path = source_file(source)
    inline = path.suffix.lower() in INLINE_TYPES
    return FileResponse(
        path, filename=path.name, content_disposition_type="inline" if inline else "attachment"
    )


@router.delete("/documents", status_code=204, dependencies=[Depends(require_admin)])
def delete_document(source: str, store: StoreDep) -> None:
    """Remove a document from the index. The file itself stays on disk."""
    if source not in store.sources():
        raise HTTPException(404, "No indexed document with this source")
    store.delete_source(source)


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
