from typing import Literal

from pydantic import BaseModel, Field


class ChatMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(max_length=20_000)


class QueryRequest(BaseModel):
    question: str = Field(min_length=3, max_length=1000)
    history: list[ChatMessage] = Field(default_factory=list, max_length=20)
    source: str | None = Field(default=None, description="Restrict search to one document")


class Source(BaseModel):
    source: str = Field(description="Path of the course file")
    title: str
    page: int | None = Field(default=None, description="Slide or page number")
    location: str = Field(description="Where to read more, e.g. 'Hydatidose — diapo 12'")
    chunk_index: int
    score: float
    text: str


class QueryResponse(BaseModel):
    answer: str
    sources: list[Source]


class IngestResponse(BaseModel):
    filename: str
    chunks: int


class DocumentInfo(BaseModel):
    source: str = Field(description="Path of the course file, as answers cite it")
    title: str
    type: str
    chunks: int
    textbook: bool = Field(description="Ranked after the course slides")
    openable: bool = Field(description="The original file can be opened from the app")


class DocumentList(BaseModel):
    documents: list[DocumentInfo]
    uploads_enabled: bool = Field(description="An admin token is configured on the server")
    upload_types: list[str]
