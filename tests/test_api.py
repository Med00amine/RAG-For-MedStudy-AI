import json

import anthropic
import httpx2
import pytest
from fastapi.testclient import TestClient

from app.api.dependencies import get_ingestion_service, get_rag_service
from app.core.config import get_settings
from app.main import app
from app.retrieval.retriever import Retriever
from app.services.ingestion_service import IngestionService
from app.services.rag_service import RagService
from tests.test_rag_service import FakeLLM


@pytest.fixture
def client(fake_embedder, store, tmp_path, monkeypatch):
    monkeypatch.setattr(get_settings(), "upload_dir", str(tmp_path))
    retriever = Retriever(fake_embedder, store, top_k=3, min_score=0.5)
    app.dependency_overrides[get_ingestion_service] = lambda: IngestionService(fake_embedder, store)
    app.dependency_overrides[get_rag_service] = lambda: RagService(retriever, FakeLLM())
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_upload_then_query(client):
    upload = client.post("/documents", files={"file": ("pets.txt", b"My cat sleeps all day.")})
    assert upload.status_code == 201
    assert upload.json() == {"filename": "pets.txt", "chunks": 1}

    response = client.post("/query", json={"question": "What does the cat do?"})

    assert response.status_code == 200
    body = response.json()
    assert body["answer"] == "Cats sleep a lot [1]."
    assert body["sources"][0]["source"] == "pets.txt"


def test_upload_rejects_unsupported_type(client):
    response = client.post("/documents", files={"file": ("lecture.mp4", b"...")})
    assert response.status_code == 415


def test_query_validation(client):
    assert client.post("/query", json={"question": ""}).status_code == 422


class BrokenLLM:
    def stream(self, system, messages):
        request = httpx2.Request("POST", "https://api.anthropic.com")
        raise anthropic.APIConnectionError(request=request)
        yield  # makes this a generator, like a real streaming client


def use_broken_llm(client, fake_embedder, store):
    retriever = Retriever(fake_embedder, store, top_k=3, min_score=0.5)
    app.dependency_overrides[get_rag_service] = lambda: RagService(retriever, BrokenLLM())
    client.post("/documents", files={"file": ("pets.txt", b"My cat sleeps all day.")})


def test_llm_failure_returns_502(client, fake_embedder, store):
    use_broken_llm(client, fake_embedder, store)

    response = client.post("/query", json={"question": "What does the cat do?"})

    assert response.status_code == 502


def test_chat_streams_sources_then_tokens(client):
    client.post("/documents", files={"file": ("pets.txt", b"My cat sleeps all day.")})

    response = client.post(
        "/chat",
        json={
            "question": "What does the cat do?",
            "history": [
                {"role": "user", "content": "Hi"},
                {"role": "assistant", "content": "Hello"},
            ],
        },
    )

    events = [json.loads(line) for line in response.text.splitlines()]
    assert response.headers["content-type"] == "application/x-ndjson"
    assert events[0]["type"] == "sources"
    assert events[0]["sources"][0]["title"] == "pets"
    assert "".join(e["text"] for e in events if e["type"] == "token") == "Cats sleep a lot [1]."
    assert events[-1] == {"type": "done"}


def test_chat_reports_llm_failure_in_stream(client, fake_embedder, store):
    use_broken_llm(client, fake_embedder, store)

    response = client.post("/chat", json={"question": "What does the cat do?"})

    events = [json.loads(line) for line in response.text.splitlines()]
    assert [e["type"] for e in events] == ["sources", "error", "done"]
