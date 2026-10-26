from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, UploadFile

from app.api.dependencies import get_ingestion_service, get_rag_service
from app.core.config import get_settings
from app.ingestion.loader import SUPPORTED_EXTENSIONS
from app.schemas.rag import IngestResponse, QueryRequest, QueryResponse, Source
from app.services.ingestion_service import IngestionService
from app.services.rag_service import RagService

router = APIRouter()

IngestionDep = Annotated[IngestionService, Depends(get_ingestion_service)]
RagDep = Annotated[RagService, Depends(get_rag_service)]


@router.post("/documents", response_model=IngestResponse, status_code=201)
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
    result = service.ask(req.question, source=req.source)
    return QueryResponse(
        answer=result.answer,
        sources=[
            Source(
                source=r.metadata["source"],
                chunk_index=r.metadata["chunk_index"],
                score=round(r.score, 4),
                text=r.text,
            )
            for r in result.sources
        ],
    )
