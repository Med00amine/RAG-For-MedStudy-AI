from pydantic import BaseModel, Field


class QueryRequest(BaseModel):
    question: str = Field(min_length=3, max_length=1000)
    source: str | None = Field(default=None, description="Restrict search to one document")


class Source(BaseModel):
    source: str
    chunk_index: int
    score: float
    text: str


class QueryResponse(BaseModel):
    answer: str
    sources: list[Source]


class IngestResponse(BaseModel):
    filename: str
    chunks: int
